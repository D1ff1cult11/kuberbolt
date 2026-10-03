package gateway

import (
	"context"
	"fmt"
	"net"
	"time"

	"github.com/kuberbolt/financial-pod/internal/brain"
	"github.com/kuberbolt/financial-pod/internal/budget"
	"github.com/kuberbolt/financial-pod/internal/cache"
	"github.com/kuberbolt/financial-pod/internal/config"
	"github.com/kuberbolt/financial-pod/internal/l402"
	"github.com/kuberbolt/financial-pod/internal/ledger"
	"github.com/kuberbolt/financial-pod/internal/ln"
	"github.com/kuberbolt/financial-pod/internal/pb"
	"go.uber.org/zap"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// ErrPaymentRequired is returned by ProviderSide when a request lacks credentials.
// RequesterSide type-asserts this to extract the challenge details.
type ErrPaymentRequired struct {
	Invoice     string
	MacaroonHex string
	PaymentHash string
	AmountMSat  int64
	ExpirySec   int32
}

func (e *ErrPaymentRequired) Error() string {
	return fmt.Sprintf("402 Payment Required: %d msat, hash=%s",
		e.AmountMSat, shortStr(e.PaymentHash, 12))
}

// Server is the top-level Financial Pod that combines:
//   - ProviderSide: accepts inbound L402-gated requests
//   - RequesterSide: makes outbound L402 payments to other pods
//   - gRPC server: listens for incoming connections
type Server struct {
	pb.UnimplementedFinancialPodServiceServer

	cfg       *config.Config
	logger    *zap.Logger
	lnd       ln.ClientInterface
	db        *ledger.DB
	budget    *budget.Manager
	invoices  *cache.InvoiceCache
	macMgr    *l402.Manager
	provider  *ProviderSide
	requester *RequesterSide
	grpc      *grpc.Server
}

// NewServer constructs the Financial Pod. It connects to LND and opens the ledger.
// Returns an error if LND is unreachable or the database cannot be opened.
func NewServer(ctx context.Context, cfg *config.Config, logger *zap.Logger) (*Server, error) {
	// 1. Connect to this agent's LND node.
	lndClient, err := ln.NewClient(ctx, &ln.Config{
		Host:         cfg.Lightning.LNDHost,
		GRPCPort:     cfg.Lightning.LNDGRPCPort,
		TLSCertPath:  cfg.Lightning.TLSCertPath,
		MacaroonPath: cfg.Lightning.MacaroonPath,
	}, logger)
	if err != nil {
		return nil, fmt.Errorf("gateway: LND connection failed: %w", err)
	}

	// 2. Open SQLite ledger.
	dbPath := fmt.Sprintf("%s/ledger.db", config.DefaultDir(cfg.Agent.Name))
	db, err := ledger.Open(dbPath)
	if err != nil {
		lndClient.Close()
		return nil, fmt.Errorf("gateway: open ledger: %w", err)
	}

	// 3. Load persisted spend from ledger into budget manager.
	bm := budget.NewManager(cfg.Budget, logger)
	dailySpent, _ := db.SumOutgoingSettledToday()
	monthlySpent, _ := db.SumOutgoingSettledThisMonth()
	bm.LoadSpend(dailySpent, monthlySpent)

	// 4. Build sub-systems.
	invoices := cache.New()

	// Root key for macaroon signing — derived from agent's Nostr private key.
	macRootKey := deriveRootKey(cfg.Agent.NostrPrivKey)
	macMgr := l402.NewManager(macRootKey)

	servicePriceMSat := int64(0)
	if len(cfg.Services) > 0 {
		servicePriceMSat = cfg.Services[0].PriceMSat
	}

	brainClient, err := brain.NewHTTPClient(cfg.Brain.URL)
	if err != nil {
		db.Close()
		lndClient.Close()
		return nil, fmt.Errorf("gateway: configure Brain client: %w", err)
	}
	provider := newProviderSide(lndClient, macMgr, invoices, db, servicePriceMSat, logger, brainClient)
	requester := newRequesterSide(lndClient, bm, db, logger)

	return &Server{
		cfg:       cfg,
		logger:    logger,
		lnd:       lndClient,
		db:        db,
		budget:    bm,
		invoices:  invoices,
		macMgr:    macMgr,
		provider:  provider,
		requester: requester,
	}, nil
}

// Start begins the gRPC listener and background maintenance tasks.
func (s *Server) Start(ctx context.Context) error {
	addr := fmt.Sprintf("0.0.0.0:%d", s.cfg.Network.GRPCPort)
	lis, err := net.Listen("tcp", addr)
	if err != nil {
		return fmt.Errorf("gateway: listen %s: %w", addr, err)
	}

	s.grpc = grpc.NewServer(
		grpc.UnaryInterceptor(s.l402Interceptor),
	)

	pb.RegisterFinancialPodServiceServer(s.grpc, s)

	go func() {
		s.logger.Info("gRPC server listening", zap.String("addr", addr))
		if err := s.grpc.Serve(lis); err != nil && err != grpc.ErrServerStopped {
			s.logger.Error("gRPC server error", zap.Error(err))
		}
	}()

	go s.backgroundTasks(ctx)

	return nil
}

// l402Interceptor checks for L402 credentials on every incoming gRPC call.
// Management RPCs pass through without payment enforcement.
func (s *Server) l402Interceptor(
	ctx context.Context,
	req interface{},
	info *grpc.UnaryServerInfo,
	handler grpc.UnaryHandler,
) (interface{}, error) {
	switch info.FullMethod {
	case "/kuberbolt.v1.FinancialPodService/GetBudgetInfo",
		"/kuberbolt.v1.FinancialPodService/GetChannelInfo",
		"/kuberbolt.v1.FinancialPodService/PayHoldInvoice":
		return handler(ctx, req)
	}
	return handler(ctx, req)
}

// backgroundTasks runs periodic maintenance: cache cleanup.
func (s *Server) backgroundTasks(ctx context.Context) {
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			if n := s.invoices.CleanupExpired(); n > 0 {
				s.logger.Info("cleaned up expired invoice cache entries", zap.Int("count", n))
			}
		}
	}
}

// Stop gracefully shuts down all components.
func (s *Server) Stop(_ context.Context) error {
	if s.grpc != nil {
		s.grpc.GracefulStop()
	}
	if s.db != nil {
		s.db.Close()
	}
	if s.lnd != nil {
		s.lnd.Close()
	}
	return nil
}

// CallService routes an inbound request through the provider-side L402 handler.
// Implements financialPodServiceServer.
func (s *Server) CallService(ctx context.Context, req *pb.CallServiceRequest) (*pb.CallServiceResponse, error) {
	response, err := s.provider.HandleCallService(ctx, req)
	if paymentRequired, ok := err.(*ErrPaymentRequired); ok {
		return nil, paymentRequiredStatus(paymentRequired)
	}
	return response, err
}

// PayHoldInvoice triggers an outgoing payment from this node's wallet.
// Implements financialPodServiceServer.
func (s *Server) PayHoldInvoice(ctx context.Context, req *pb.PayHoldInvoiceRequest) (*pb.PayHoldInvoiceResponse, error) {
	preimage, err := s.lnd.SendPayment(ctx, req.Invoice, defaultPaymentTimeoutSec)
	if err != nil {
		return &pb.PayHoldInvoiceResponse{Success: false, Status: "failed"}, nil
	}
	return &pb.PayHoldInvoiceResponse{
		Success:  true,
		Status:   "settled",
		Preimage: fmt.Sprintf("%x", preimage),
	}, nil
}

// GetBudgetInfo returns current budget counters.
func (s *Server) GetBudgetInfo(_ context.Context, _ *pb.GetBudgetInfoRequest) (*pb.GetBudgetInfoResponse, error) {
	return &pb.GetBudgetInfoResponse{
		DailyLimitMsat:   s.cfg.Budget.DailyLimitMSat,
		DailySpentMsat:   s.budget.GetDailySpent(),
		MonthlyLimitMsat: s.cfg.Budget.MonthlyLimitMSat,
		MonthlySpentMsat: s.budget.GetMonthlySpent(),
		AvailableMsat:    s.budget.GetDailyAvailable(),
	}, nil
}

<<<<<<< HEAD
// GetChannelInfo returns readiness data (e.g., LND chain sync status).
func (s *Server) GetChannelInfo(ctx context.Context, _ *pb.GetChannelInfoRequest) (*pb.GetChannelInfoResponse, error) {
	info, err := s.lnd.GetInfo(ctx)
	if err != nil {
		return nil, fmt.Errorf("LND not ready: %w", err)
	}
	return &pb.GetChannelInfoResponse{
		SyncedToChain: info.SyncedToChain,
	}, nil
}

// financialPodServiceServer is the interface the Server fulfils for gRPC registration.
type financialPodServiceServer interface {
	CallService(context.Context, *pb.CallServiceRequest) (*pb.CallServiceResponse, error)
	PayHoldInvoice(context.Context, *pb.PayHoldInvoiceRequest) (*pb.PayHoldInvoiceResponse, error)
	GetBudgetInfo(context.Context, *pb.GetBudgetInfoRequest) (*pb.GetBudgetInfoResponse, error)
	GetChannelInfo(context.Context, *pb.GetChannelInfoRequest) (*pb.GetChannelInfoResponse, error)
}

// financialPodServiceDesc is the minimal gRPC service descriptor, replacing protoc output.
var financialPodServiceDesc = grpc.ServiceDesc{
	ServiceName: "kuberbolt.v1.FinancialPodService",
	HandlerType: (*financialPodServiceServer)(nil),
	Methods: []grpc.MethodDesc{
		{
			MethodName: "CallService",
			Handler: func(srv interface{}, ctx context.Context, dec func(interface{}) error, _ grpc.UnaryServerInterceptor) (interface{}, error) {
				var req pb.CallServiceRequest
				if err := dec(&req); err != nil {
					return nil, err
				}
				return srv.(financialPodServiceServer).CallService(ctx, &req)
			},
		},
		{
			MethodName: "PayHoldInvoice",
			Handler: func(srv interface{}, ctx context.Context, dec func(interface{}) error, _ grpc.UnaryServerInterceptor) (interface{}, error) {
				var req pb.PayHoldInvoiceRequest
				if err := dec(&req); err != nil {
					return nil, err
				}
				return srv.(financialPodServiceServer).PayHoldInvoice(ctx, &req)
			},
		},
		{
			MethodName: "GetBudgetInfo",
			Handler: func(srv interface{}, ctx context.Context, dec func(interface{}) error, _ grpc.UnaryServerInterceptor) (interface{}, error) {
				var req pb.GetBudgetInfoRequest
				if err := dec(&req); err != nil {
					return nil, err
				}
				return srv.(financialPodServiceServer).GetBudgetInfo(ctx, &req)
			},
		},
		{
			MethodName: "GetChannelInfo",
			Handler: func(srv interface{}, ctx context.Context, dec func(interface{}) error, _ grpc.UnaryServerInterceptor) (interface{}, error) {
				var req pb.GetChannelInfoRequest
				if err := dec(&req); err != nil {
					return nil, err
				}
				return srv.(financialPodServiceServer).GetChannelInfo(ctx, &req)
			},
		},
	},
	Streams:  []grpc.StreamDesc{},
	Metadata: "agent_service.proto",
=======
// paymentRequiredStatus is the network-safe representation of an L402
// challenge. A Go error value cannot cross a gRPC connection by itself.
func paymentRequiredStatus(err *ErrPaymentRequired) error {
	st := status.New(codes.PermissionDenied, "payment required")
	withDetails, detailsErr := st.WithDetails(&pb.PaymentRequired{
		Invoice:     err.Invoice,
		MacaroonHex: err.MacaroonHex,
		PaymentHash: err.PaymentHash,
		AmountMsat:  err.AmountMSat,
		ExpirySec:   err.ExpirySec,
	})
	if detailsErr != nil {
		return st.Err()
	}
	return withDetails.Err()
>>>>>>> feat/system-wiring
}

// deriveRootKey produces a 32-byte macaroon signing key from the agent's hex private key.
func deriveRootKey(privKeyHex string) []byte {
	key := make([]byte, 32)
	for i := 0; i < 32 && i*2+2 <= len(privKeyHex); i++ {
		fmt.Sscanf(privKeyHex[i*2:i*2+2], "%02x", &key[i])
	}
	return key
}
