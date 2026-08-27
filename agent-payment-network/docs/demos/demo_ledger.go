package main
import (
	"fmt"
	"log"
	"os"
	"time"
	"github.com/kuberbolt/fp/ledger"
)
func main() {
	fmt.Println("==================================================")
	fmt.Println(" KUBERBOLT FP LEDGER DEMO")
	fmt.Println("==================================================")
	dbPath := "demo_ledger.db"
	os.Remove(dbPath)
	fmt.Printf("[1] Initializing SQLite ledger at %s...\n", dbPath)
	db, err := ledger.NewLedger(dbPath)
	if err != nil {
		log.Fatalf("Failed to init ledger: %v", err)
	}
	defer db.Close()
	fmt.Println("\n[2] Simulating Provider receiving an HTLC Hold request...")
	rhash := "abc123hash"
	preimage := "secret_preimage_789"
	jobID := "job_ai_render_001"
	err = db.RecordPaymentHold(&ledger.PaymentHold{
		HoldID:            "hold_001",
		RHash:             rhash,
		Preimage:          preimage,
		HTLCTimeoutBlocks: 40,
		JobID:             jobID,
	})
	if err != nil {
		log.Fatalf("Failed to record hold: %v", err)
	}
	fmt.Printf("    -> Recorded Payment Hold: Job %s, Hash %s, Secret %s\n", jobID, rhash, preimage)
	fmt.Println("\n[3] Simulating Client paying the invoice...")
	txID := "tx_100"
	err = db.RecordTransaction(&ledger.Transaction{
		ID:              txID,
		Direction:       "RECEIVED",
		AgentPubkey:     "client_pubkey_xyz",
		AmountMSat:      50000,
		Status:          "PENDING",
		HoldInvoiceHash: rhash,
		CreatedAt:       time.Now(),
		Notes:           "Waiting for job completion",
	})
	if err != nil {
		log.Fatalf("Failed to record transaction: %v", err)
	}
	fmt.Printf("    -> Transaction %s logged as PENDING (HTLC Locked).\n", txID)
	fmt.Println("\n[4] Simulating Job Completion...")
	hold, err := db.GetPaymentHold(rhash)
	if err != nil {
		log.Fatalf("Failed to get hold: %v", err)
	}
	fmt.Printf("    -> Retrieved secret preimage for Hash %s: %s\n", rhash, hold.Preimage)
	fmt.Printf("    -> Submitting Preimage to LND to claim funds...\n")
	err = db.UpdateTransactionStatus(txID, "SETTLED", hold.Preimage)
	if err != nil {
		log.Fatalf("Failed to update status: %v", err)
	}
	fmt.Printf("    -> Transaction %s updated to SETTLED in ledger!\n", txID)
	fmt.Println("\n==================================================")
	fmt.Println(" LEDGER DEMO COMPLETE")
	fmt.Println("==================================================")
}