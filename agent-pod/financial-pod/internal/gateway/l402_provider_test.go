package gateway

import (
	"context"
	"crypto/rand"
	"testing"
	"time"

	"github.com/kuberbolt/financial-pod/internal/cache"
	"github.com/kuberbolt/financial-pod/internal/l402"
	"github.com/kuberbolt/financial-pod/internal/ln"
	"github.com/kuberbolt/financial-pod/internal/pb"
	"go.uber.org/zap"
)

func TestL402ProviderFlow(t *testing.T) {
	logger := zap.NewNop()
	db := setupTestDB(t)

	mockLN := &MockLNClient{}

	macKey := make([]byte, 32)
	rand.Read(macKey)
	macMgr := l402.NewManager(macKey)
	invoices := cache.New()

	provider := newProviderSide(mockLN, macMgr, invoices, db, 1000, logger)

	ctx := context.Background()
	req := &pb.CallServiceRequest{}

	// Phase 1: Unauthenticated request should return 402 challenge
	resp, err := provider.HandleCallService(ctx, req)
	if resp != nil {
		t.Fatalf("expected nil response for unauthenticated request, got %v", resp)
	}
	pErr, ok := err.(*ErrPaymentRequired)
	if !ok {
		t.Fatalf("expected ErrPaymentRequired, got %T: %v", err, err)
	}
	if pErr.Invoice != "mock_invoice" {
		t.Errorf("expected invoice 'mock_invoice', got %q", pErr.Invoice)
	}
	if pErr.AmountMSat != 1000 {
		t.Errorf("expected amount 1000, got %d", pErr.AmountMSat)
	}

	cached := invoices.GetByRHash(pErr.PaymentHash)
	if cached == nil {
		t.Fatalf("expected invoice in cache for rhash %s", pErr.PaymentHash)
	}

	// Phase 2: Authenticated request
	mockLN.SubscribeSingleInvoiceFunc = func(ctx context.Context, rhash []byte) (<-chan ln.InvoiceUpdate, error) {
		ch := make(chan ln.InvoiceUpdate, 1)
		ch <- ln.InvoiceUpdate{
			State:   ln.InvoiceAccepted,
			RHash:   rhash,
			AmtMSat: 1000,
		}
		close(ch)
		return ch, nil
	}

	var settledPreimage []byte
	mockLN.SettleInvoiceFunc = func(ctx context.Context, preimage []byte) error {
		settledPreimage = preimage
		return nil
	}

	authReq := &pb.CallServiceRequest{
		JobSpec:     []byte("test_job"),
		MacaroonHex: pErr.MacaroonHex,
		// No PreimageHex — provider confirms payment via LND HTLC state,
		// not by client-supplied preimage.
	}

	authResp, authErr := provider.HandleCallService(ctx, authReq)
	if authErr != nil {
		t.Fatalf("authenticated request failed: %v", authErr)
	}
	if authResp.Status != "success" {
		t.Errorf("expected status 'success', got %q", authResp.Status)
	}
	if string(authResp.OutputData) != "test_job" {
		t.Errorf("expected OutputData 'test_job', got %q", string(authResp.OutputData))
	}

	if string(settledPreimage) != string(cached.Preimage) {
		t.Errorf("settled preimage mismatch")
	}

	// Ensure cache is cleared
	if invoices.GetByRHash(pErr.PaymentHash) != nil {
		t.Errorf("cache was not cleared after settlement")
	}
}

// A payment that never locks must not hang the provider: the wait ends at the
// challenge TTL and the hold invoice is cancelled.
func TestL402ProviderCancelsWhenHTLCNeverArrives(t *testing.T) {
	macKey := make([]byte, 32)
	rand.Read(macKey)
	invoices := cache.New()
	cancelled := false
	mockLN := &MockLNClient{
		SubscribeSingleInvoiceFunc: func(ctx context.Context, rhash []byte) (<-chan ln.InvoiceUpdate, error) {
			ch := make(chan ln.InvoiceUpdate, 1)
			go func() { <-ctx.Done(); ch <- ln.InvoiceUpdate{Err: ctx.Err()}; close(ch) }()
			return ch, nil
		},
		CancelInvoiceFunc: func(ctx context.Context, paymentHash []byte) error { cancelled = true; return nil },
		SettleInvoiceFunc: func(ctx context.Context, preimage []byte) error {
			t.Fatal("settled an invoice that was never paid")
			return nil
		},
	}
	provider := newProviderSide(mockLN, l402.NewManager(macKey), invoices, setupTestDB(t), 1000, zap.NewNop())

	_, err := provider.HandleCallService(context.Background(), &pb.CallServiceRequest{})
	challenge := err.(*ErrPaymentRequired)
	invoices.GetByRHash(challenge.PaymentHash).ExpiresAt = time.Now().Add(50 * time.Millisecond)

	done := make(chan error, 1)
	go func() {
		_, err := provider.HandleCallService(context.Background(), &pb.CallServiceRequest{MacaroonHex: challenge.MacaroonHex})
		done <- err
	}()
	select {
	case err := <-done:
		if err == nil {
			t.Fatal("expected an error when the HTLC never arrives")
		}
	case <-time.After(5 * time.Second):
		t.Fatal("provider hung waiting for an HTLC that never arrived")
	}
	if !cancelled {
		t.Error("hold invoice was not cancelled")
	}
	if invoices.GetByRHash(challenge.PaymentHash) != nil {
		t.Error("challenge was not removed from the cache")
	}
}
