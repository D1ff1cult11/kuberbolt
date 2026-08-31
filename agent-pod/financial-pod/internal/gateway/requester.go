package gateway

import (
	"context"
	"encoding/hex"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/kuberbolt/financial-pod/internal/budget"
	"github.com/kuberbolt/financial-pod/internal/ledger"
	"github.com/kuberbolt/financial-pod/internal/ln"
	"github.com/kuberbolt/financial-pod/internal/pb"
	"go.uber.org/zap"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

// defaultPaymentTimeoutSec is how long SendPayment blocks waiting for HODL to settle.
const defaultPaymentTimeoutSec = 120

// RequesterSide handles all outbound service calls: detects 402 challenges,
// pays invoices, extracts preimages, and retries with credentials.
type RequesterSide struct {
	lnd    *ln.Client
	budget *budget.Manager
	db     *ledger.DB
	logger *zap.Logger
}

func newRequesterSide(
	lnd *ln.Client,
	bm *budget.Manager,
	db *ledger.DB,
	logger *zap.Logger,
) *RequesterSide {
	return &RequesterSide{
		lnd:    lnd,
		budget: bm,
		db:     db,
		logger: logger,
	}
}

// CallProvider executes the full client-side L402 flow against a remote provider FP:
//
//  1. Dial the provider's gRPC endpoint.
//  2. Send unauthenticated CallService → receive 402 with invoice + macaroon.
//  3. Check budget.
//  4. Pay the HODL invoice via SendPaymentV2 → receive preimage on ACCEPTED.
//  5. Retry CallService with macaroon + preimage headers.
//  6. Return the result to the caller.
func (r *RequesterSide) CallProvider(
	ctx context.Context,
	providerAddr string,
	req *pb.CallServiceRequest,
) (*pb.CallServiceResponse, error) {

	// 1. Dial provider FP (plain text for now; TLS between pods added in Phase 5).
	conn, err := grpc.DialContext(ctx, providerAddr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		return nil, fmt.Errorf("requester: dial %s: %w", providerAddr, err)
	}
	defer conn.Close()

	// 2. Send unauthenticated request — expect a PaymentRequired error.
	challenge, err := r.sendUnauthenticated(ctx, conn, req)
	if err != nil {
		return nil, fmt.Errorf("requester: unauthenticated call: %w", err)
	}

	r.logger.Info("received L402 challenge",
		zap.String("payment_hash", challenge.PaymentHash[:12]+"…"),
		zap.Int64("amount_msat", challenge.AmountMSat),
	)

	// 3. Check budget before paying.
	if err := r.budget.CheckBudgetFor(ctx, challenge.AmountMSat); err != nil {
		return nil, fmt.Errorf("requester: budget check: %w", err)
	}

	// 4. Record pending outgoing payment.
	jobID := uuid.New().String()
	if err := r.db.RecordTransaction(&ledger.Transaction{
		JobID:              jobID,
		CounterpartyPubkey: providerAddr,
		Direction:          "outgoing",
		AmountMSat:         challenge.AmountMSat,
		InvoicePaymentHash: challenge.PaymentHash,
		MacaroonID:         challenge.MacaroonHex[:16],
		Status:             "pending",
		CreatedAt:          time.Now(),
	}); err != nil {
		r.logger.Warn("failed to record pending outgoing transaction", zap.Error(err))
	}

	// 5. Pay the HODL invoice. For HODL invoices, SendPayment returns the preimage
	//    once the provider settles — which happens AFTER compute succeeds.
	//    The call blocks until settled or timeout.
	r.logger.Info("paying HODL invoice",
		zap.String("payment_hash", challenge.PaymentHash[:12]+"…"),
	)
	preimageBytes, err := r.lnd.SendPayment(ctx, challenge.Invoice, defaultPaymentTimeoutSec)
	if err != nil {
		_ = r.db.UpdateStatus(jobID, "cancelled")
		return nil, fmt.Errorf("requester: payment failed: %w", err)
	}
	preimageHex := hex.EncodeToString(preimageBytes)

	r.logger.Info("payment completed, retrying with preimage",
		zap.String("preimage_prefix", preimageHex[:8]+"…"),
	)

	// 6. Retry the original request with macaroon + preimage.
	authReq := &pb.CallServiceRequest{
		ServiceKind: req.ServiceKind,
		JobSpec:     req.JobSpec,
		MacaroonHex: challenge.MacaroonHex,
		PreimageHex: preimageHex,
	}
	result, err := r.sendAuthenticated(ctx, conn, authReq)
	if err != nil {
		// Payment was already made; log but don't mark as cancelled.
		r.logger.Error("authenticated retry failed after payment", zap.Error(err))
		_ = r.db.UpdateStatus(jobID, "expired")
		return nil, fmt.Errorf("requester: authenticated retry: %w", err)
	}

	// 7. Record spend in budget and mark ledger as settled.
	r.budget.RecordSpend(challenge.AmountMSat)
	_ = r.db.UpdateStatus(jobID, "settled")

	r.logger.Info("CallProvider completed successfully",
		zap.String("job_id", jobID),
		zap.Int64("amount_msat", challenge.AmountMSat),
	)

	return result, nil
}

// sendUnauthenticated calls CallService without auth credentials and expects
// a PaymentRequired error back. Returns the parsed challenge or an error.
func (r *RequesterSide) sendUnauthenticated(
	ctx context.Context,
	conn *grpc.ClientConn,
	req *pb.CallServiceRequest,
) (*pb.PaymentRequired, error) {
	// We use raw gRPC Invoke since we hand-wrote the types.
	var challenge pb.PaymentRequired
	err := conn.Invoke(ctx, "/kuberbolt.v1.FinancialPodService/CallService", req, &challenge)
	if err == nil {
		// Provider responded without a challenge — unexpected but handle gracefully.
		return nil, fmt.Errorf("requester: expected 402 challenge, got success response")
	}

	// Parse the PaymentRequired details from the gRPC status error.
	parsed, parseErr := parsePaymentRequired(err)
	if parseErr != nil {
		return nil, fmt.Errorf("requester: unexpected error (not a 402): %w", err)
	}
	return parsed, nil
}

// sendAuthenticated retries the request with macaroon + preimage headers.
func (r *RequesterSide) sendAuthenticated(
	ctx context.Context,
	conn *grpc.ClientConn,
	req *pb.CallServiceRequest,
) (*pb.CallServiceResponse, error) {
	var resp pb.CallServiceResponse
	err := conn.Invoke(ctx, "/kuberbolt.v1.FinancialPodService/CallService", req, &resp)
	if err != nil {
		return nil, fmt.Errorf("authenticated call failed: %w", err)
	}
	return &resp, nil
}

// parsePaymentRequired extracts PaymentRequired details from a gRPC error.
// The provider encodes the challenge as a structured error detail.
func parsePaymentRequired(err error) (*pb.PaymentRequired, error) {
	pErr, ok := err.(*ErrPaymentRequired)
	if !ok {
		return nil, fmt.Errorf("not a PaymentRequired error")
	}
	return &pb.PaymentRequired{
		Invoice:     pErr.Invoice,
		MacaroonHex: pErr.MacaroonHex,
		PaymentHash: pErr.PaymentHash,
		AmountMSat:  pErr.AmountMSat,
		ExpirySec:   pErr.ExpirySec,
	}, nil
}
