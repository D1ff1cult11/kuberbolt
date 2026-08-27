package main

import (
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/kuberbolt/fp/ledger"
)

const (
	colorReset  = "\033[0m"
	colorRed    = "\033[31m"
	colorGreen  = "\033[32m"
	colorYellow = "\033[33m"
	colorBlue   = "\033[34m"
	colorCyan   = "\033[36m"
	colorBold   = "\033[1m"
)

func header(title string) {
	line := strings.Repeat("=", 60)
	fmt.Printf("\n%s%s%s\n", colorCyan, line, colorReset)
	fmt.Printf("%s%s %s%s\n", colorBold, colorCyan, title, colorReset)
	fmt.Printf("%s%s%s\n\n", colorCyan, line, colorReset)
}

func step(num int, msg string) {
	fmt.Printf("%s[Step %d]%s %s\n", colorYellow, num, colorReset, msg)
}

func success(msg string) {
	fmt.Printf("  %s✓ %s%s\n", colorGreen, msg, colorReset)
}

func fail(msg string) {
	fmt.Printf("  %s✗ %s%s\n", colorRed, msg, colorReset)
}

func info(label, value string) {
	fmt.Printf("  %s%-20s%s %s\n", colorBlue, label+":", colorReset, value)
}

type Macaroon struct {
	ID         string
	RootSecret []byte
	PayHash    string
	ExpiresAt  int64
	Signature  string
}

func bakeMacaroon(rootSecret []byte, paymentHash string, ttlSeconds int64) *Macaroon {
	mac := &Macaroon{
		ID:         fmt.Sprintf("mac_%s", paymentHash[:12]),
		RootSecret: rootSecret,
		PayHash:    paymentHash,
		ExpiresAt:  time.Now().Unix() + ttlSeconds,
	}
	h := hmac.New(sha256.New, rootSecret)
	h.Write([]byte(fmt.Sprintf("account=%s|expires=%d", paymentHash, mac.ExpiresAt)))
	mac.Signature = hex.EncodeToString(h.Sum(nil))
	return mac
}

func verifyMacaroon(rootSecret []byte, mac *Macaroon) (bool, string) {
	if time.Now().Unix() > mac.ExpiresAt {
		return false, "EXPIRED"
	}
	h := hmac.New(sha256.New, rootSecret)
	h.Write([]byte(fmt.Sprintf("account=%s|expires=%d", mac.PayHash, mac.ExpiresAt)))
	expected := hex.EncodeToString(h.Sum(nil))
	if mac.Signature != expected {
		return false, "INVALID SIGNATURE"
	}
	return true, "VALID"
}

func verifyPreimage(preimageHex, rhashHex string) bool {
	preimageBytes, _ := hex.DecodeString(preimageHex)
	hash := sha256.Sum256(preimageBytes)
	return hex.EncodeToString(hash[:]) == rhashHex
}

type BudgetManager struct {
	DailyLimitMSat  int64
	DailySpentMSat  int64
}

func (bm *BudgetManager) CheckAndSpend(amount int64) (bool, string) {
	if bm.DailySpentMSat+amount > bm.DailyLimitMSat {
		return false, fmt.Sprintf("REJECTED: %d msat would exceed daily limit of %d msat (spent: %d)",
			amount, bm.DailyLimitMSat, bm.DailySpentMSat)
	}
	bm.DailySpentMSat += amount
	return true, fmt.Sprintf("APPROVED: spent %d/%d msat", bm.DailySpentMSat, bm.DailyLimitMSat)
}

func main() {
	os.Remove("demo_l402.db")

	header("KUBERBOLT L402 + HTLC FULL LIFECYCLE DEMO")
	fmt.Println("This demo simulates the complete SRS §6.5 payment flow:")
	fmt.Println("  Client FP  →  Request Service  →  Provider FP")
	fmt.Println("  Provider   →  402 + Macaroon + Invoice  →  Client")
	fmt.Println("  Client     →  Pay HTLC (lock funds)     →  Lightning")
	fmt.Println("  Client     →  Retry + Macaroon:Preimage →  Provider")
	fmt.Println("  Provider   →  Verify → Compute → Settle →  Client")
	fmt.Println()

	// ─── SETUP ───

	step(1, "Initializing SQLite Ledger (pure Go, no CGO)")
	db, err := ledger.NewLedger("demo_l402.db")
	if err != nil {
		fail(fmt.Sprintf("Ledger init failed: %v", err))
		return
	}
	defer db.Close()
	success("Ledger initialized with 3 tables: ledger, payment_holds, service_registry")

	rootSecret := make([]byte, 32)
	rand.Read(rootSecret)
	info("Root Secret", hex.EncodeToString(rootSecret)[:24]+"...")

	clientPubkey := "npub1_client_alice_02a4f3b..."
	providerPubkey := "npub1_provider_bob_03c7d8e..."
	servicePriceMSat := uint64(50000)

	budget := &BudgetManager{
		DailyLimitMSat: 200000,
		DailySpentMSat: 0,
	}

	// ─── PHASE 1: SERVICE REQUEST (UNAUTHENTICATED) ───

	header("PHASE 1: Client Sends Unauthenticated Request")

	step(2, "Client FP sends CallService request to Provider FP")
	info("Service Kind", "5001 (Video Transcription)")
	info("Provider", providerPubkey)

	step(3, "Provider FP: No macaroon in request → L402 Challenge")

	preimageBytes := make([]byte, 32)
	rand.Read(preimageBytes)
	preimageHex := hex.EncodeToString(preimageBytes)
	rhash := sha256.Sum256(preimageBytes)
	rhashHex := hex.EncodeToString(rhash[:])
	jobID := fmt.Sprintf("job_%s", rhashHex[:8])

	info("Preimage (secret)", preimageHex[:24]+"...")
	info("RHash (SHA256)", rhashHex[:24]+"...")
	info("Job ID", jobID)

	step(4, "Provider FP: Creating HODL Invoice (funds will lock, not settle)")
	holdInvoice := fmt.Sprintf("lnbcrt%du1p...hold_invoice_rhash_%s_timeout40", servicePriceMSat/1000, rhashHex[:16])
	info("HODL Invoice", holdInvoice)
	info("Amount", fmt.Sprintf("%d msat (%d sats)", servicePriceMSat, servicePriceMSat/1000))

	step(5, "Provider FP: Baking L402 Macaroon (bound to payment hash)")
	mac := bakeMacaroon(rootSecret, rhashHex, 120)
	info("Macaroon ID", mac.ID)
	info("Bound to Hash", mac.PayHash[:24]+"...")
	info("Expires", time.Unix(mac.ExpiresAt, 0).Format("15:04:05"))
	info("HMAC Signature", mac.Signature[:24]+"...")

	step(6, "Provider FP: Recording hold in ledger")
	err = db.RecordPaymentHold(&ledger.PaymentHold{
		HoldID:            fmt.Sprintf("hold_%s", rhashHex[:8]),
		RHash:             rhashHex,
		Preimage:          preimageHex,
		HTLCTimeoutBlocks: 40,
		JobID:             jobID,
	})
	if err != nil {
		fail(fmt.Sprintf("Hold record failed: %v", err))
		return
	}
	success("Payment hold recorded in SQLite")

	err = db.RecordTransaction(&ledger.Transaction{
		ID:              jobID,
		Direction:       "incoming",
		AgentPubkey:     clientPubkey,
		AmountMSat:      servicePriceMSat,
		Status:          "pending",
		HoldInvoiceHash: rhashHex,
		CreatedAt:       time.Now(),
		Notes:           "L402 challenge issued",
	})
	if err != nil {
		fail(fmt.Sprintf("Transaction record failed: %v", err))
		return
	}
	success("PENDING transaction recorded in provider ledger")

	fmt.Printf("\n  %sProvider returns HTTP 402:%s\n", colorRed, colorReset)
	fmt.Printf("  ┌─────────────────────────────────────────────┐\n")
	fmt.Printf("  │  %s402 Payment Required%s                       │\n", colorRed, colorReset)
	fmt.Printf("  │  Invoice: %s...  │\n", holdInvoice[:33])
	fmt.Printf("  │  Macaroon: %s                │\n", mac.ID)
	fmt.Printf("  │  Amount: %d msat                          │\n", servicePriceMSat)
	fmt.Printf("  └─────────────────────────────────────────────┘\n")

	// ─── PHASE 2: CLIENT PAYS HTLC ───

	header("PHASE 2: Client Pays HODL Invoice (HTLC Lock)")

	step(7, "Client FP: Budget check before payment")
	ok, reason := budget.CheckAndSpend(int64(servicePriceMSat))
	if ok {
		success(reason)
	} else {
		fail(reason)
		return
	}

	step(8, "Client FP: Paying HODL invoice via Lightning Network")
	fmt.Println("  ┌──────────────────────────────────────────┐")
	fmt.Println("  │  Client LN Node  ──HTLC──►  Provider LN │")
	fmt.Println("  │                                          │")
	fmt.Printf("  │  Funds LOCKED: %d msat               │\n", servicePriceMSat)
	fmt.Println("  │  State: ACCEPTED (not yet settled)       │")
	fmt.Println("  └──────────────────────────────────────────┘")
	success(fmt.Sprintf("HTLC locked on Lightning Network (%d msat)", servicePriceMSat))
	info("Payment Preimage", preimageHex[:24]+"...")

	// ─── PHASE 3: CLIENT RETRIES WITH MACAROON + PREIMAGE ───

	header("PHASE 3: Client Retries with Macaroon + Preimage")

	step(9, "Client FP: Retrying CallService with L402 credentials")
	info("Header macaroon", mac.ID)
	info("Header preimage", preimageHex[:24]+"...")

	step(10, "Provider FP: Verifying Macaroon")
	valid, status := verifyMacaroon(rootSecret, mac)
	if valid {
		success(fmt.Sprintf("Macaroon verification: %s", status))
	} else {
		fail(fmt.Sprintf("Macaroon verification: %s", status))
		return
	}

	step(11, "Provider FP: Verifying Preimage matches Payment Hash")
	if verifyPreimage(preimageHex, rhashHex) {
		success(fmt.Sprintf("SHA256(%s...) == %s... ✓", preimageHex[:8], rhashHex[:8]))
	} else {
		fail("Preimage does not match payment hash!")
		return
	}

	step(12, "Provider FP: Looking up hold in ledger by rhash")
	hold, err := db.GetPaymentHold(rhashHex)
	if err != nil {
		fail(fmt.Sprintf("Hold lookup failed: %v", err))
		return
	}
	success(fmt.Sprintf("Found hold: job=%s, timeout=%d blocks", hold.JobID, hold.HTLCTimeoutBlocks))

	// ─── PHASE 4: COMPUTE + SETTLE ───

	header("PHASE 4: Agent Computes → Provider Settles HODL Invoice")

	step(13, "Provider FP: Dispatching job to Agent for compute")
	fmt.Printf("  %s[Agent 2]%s Processing video transcription...\n", colorBlue, colorReset)
	time.Sleep(500 * time.Millisecond)
	computeResult := "Transcription output: 'Hello World, this is Kuberbolt agent compute.'"
	success(fmt.Sprintf("Compute complete: %s", computeResult[:40]+"..."))

	step(14, "Provider FP: Settling HODL Invoice (releasing locked funds)")
	fmt.Println("  ┌──────────────────────────────────────────┐")
	fmt.Println("  │  Provider LN Node settles HTLC           │")
	fmt.Printf("  │  Preimage revealed: %s... │\n", preimageHex[:20])
	fmt.Printf("  │  Funds DISBURSED: %d msat              │\n", servicePriceMSat)
	fmt.Println("  │  State: SETTLED                           │")
	fmt.Println("  └──────────────────────────────────────────┘")

	err = db.UpdateTransactionStatus(jobID, "settled", preimageHex)
	if err != nil {
		fail(fmt.Sprintf("Settlement update failed: %v", err))
		return
	}
	success("Transaction status updated to SETTLED in ledger")

	step(15, "Provider FP: Returning output to Client FP")
	info("Output", computeResult[:40]+"...")
	success("Output delivered to Client Agent for review")

	// ─── PHASE 5: BUDGET GUARDRAIL DEMO ───

	header("PHASE 5: Budget Guardrail Enforcement")

	step(16, "Simulating a second payment that exceeds budget")
	info("Daily Limit", fmt.Sprintf("%d msat", budget.DailyLimitMSat))
	info("Already Spent", fmt.Sprintf("%d msat", budget.DailySpentMSat))
	info("New Request", "180000 msat")

	ok2, reason2 := budget.CheckAndSpend(180000)
	if ok2 {
		success(reason2)
	} else {
		fail(reason2)
		success("Budget guardrail working correctly — prevents overspending")
	}

	// ─── PHASE 6: EXPIRED MACAROON DEMO ───

	header("PHASE 6: Expired Macaroon Rejection")

	step(17, "Creating a macaroon that expires in 0 seconds")
	expiredMac := bakeMacaroon(rootSecret, rhashHex, -1)
	valid2, status2 := verifyMacaroon(rootSecret, expiredMac)
	if !valid2 {
		fail(fmt.Sprintf("Macaroon rejected: %s", status2))
		success("Expired macaroon correctly blocked")
	}

	// ─── PHASE 7: TAMPERED MACAROON DEMO ───

	header("PHASE 7: Tampered Macaroon Rejection")

	step(18, "Forging a macaroon with wrong signature")
	forgedMac := bakeMacaroon(rootSecret, rhashHex, 120)
	forgedMac.Signature = "deadbeef" + forgedMac.Signature[8:]

	valid3, status3 := verifyMacaroon(rootSecret, forgedMac)
	if !valid3 {
		fail(fmt.Sprintf("Macaroon rejected: %s", status3))
		success("Tampered macaroon correctly blocked")
	}

	// ─── SUMMARY ───

	header("DEMO COMPLETE — SUMMARY")

	fmt.Println("  Components demonstrated:")
	fmt.Printf("  %s✓%s SQLite Ledger (pure Go, modernc.org/sqlite)\n", colorGreen, colorReset)
	fmt.Printf("  %s✓%s HTLC Hold Invoice lifecycle (PENDING → SETTLED)\n", colorGreen, colorReset)
	fmt.Printf("  %s✓%s L402 Challenge/Response (402 → pay → retry)\n", colorGreen, colorReset)
	fmt.Printf("  %s✓%s Macaroon creation with HMAC + caveats\n", colorGreen, colorReset)
	fmt.Printf("  %s✓%s Macaroon verification (valid, expired, tampered)\n", colorGreen, colorReset)
	fmt.Printf("  %s✓%s Preimage ↔ Hash verification (SHA256)\n", colorGreen, colorReset)
	fmt.Printf("  %s✓%s Budget guardrail enforcement\n", colorGreen, colorReset)
	fmt.Printf("  %s✓%s Payment hold tracking (rhash → job_id)\n", colorGreen, colorReset)
	fmt.Println()
	fmt.Println("  SRS Requirements covered:")
	fmt.Printf("  %s•%s FR-6.5.1 L402 challenge response\n", colorBlue, colorReset)
	fmt.Printf("  %s•%s FR-6.5.2 HODL invoice (simulated)\n", colorBlue, colorReset)
	fmt.Printf("  %s•%s FR-6.5.3 Client pay + retry with preimage\n", colorBlue, colorReset)
	fmt.Printf("  %s•%s FR-6.5.4 Macaroon + preimage verification\n", colorBlue, colorReset)
	fmt.Printf("  %s•%s FR-6.5.5 Settle only after compute\n", colorBlue, colorReset)
	fmt.Printf("  %s•%s FR-6.5.6 Transaction recorded in ledger\n", colorBlue, colorReset)
	fmt.Printf("  %s•%s NFR-5   Auditability (SQLite ledger)\n", colorBlue, colorReset)
	fmt.Println()

	fmt.Printf("  Database file: %sdemo_l402.db%s\n", colorGreen, colorReset)
	fmt.Println()

	os.Remove("demo_l402.db")
}
