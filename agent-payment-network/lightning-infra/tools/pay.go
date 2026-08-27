//go:build ignore

package main

import (
	"encoding/json"
	"fmt"
	"log"
	"os"

	"github.com/devlup-labs/kuberbolt/lightning-node/config"
	"github.com/devlup-labs/kuberbolt/lightning-node/docker"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Println("Usage: go run pay.go <BOLT11_PAYMENT_REQUEST>")
		os.Exit(1)
	}

	payReq := os.Args[1]

	// 1. Read guardrail limit from test-data.json
	var limit int64 = 1000
	fileBytes, err := os.ReadFile("test-data.json")
	if err == nil {
		var data config.TestData
		if err := json.Unmarshal(fileBytes, &data); err == nil && data.GuardrailParams.MaxPaymentSats > 0 {
			limit = data.GuardrailParams.MaxPaymentSats
		}
	}

	// 2. Decode the invoice
	decoded, err := docker.DecodeInvoice("lnd1", payReq)
	if err != nil {
		log.Fatalf("[!] Error decoding invoice: %v", err)
	}

	fmt.Printf("[*] Invoice Details: Amount = %d sats | Memo = %s\n", decoded.NumSatoshis, decoded.Description)

	// 3. Enforce guardrail limit
	if decoded.NumSatoshis > limit {
		fmt.Println("\n=======================================================")
		fmt.Printf("[❌ GUARDRAIL ERROR] Payment blocked!\n")
		fmt.Printf("   Invoice amount (%d sats) exceeds maximum allowed limit of %d sats.\n", decoded.NumSatoshis, limit)
		fmt.Println("=======================================================")
		os.Exit(1)
	}

	// 4. Pay invoice if within limit
	fmt.Printf("[+] Guardrail Passed (%d sats <= %d sats limit). Paying invoice...\n", decoded.NumSatoshis, limit)
	out, err := docker.ExecLND("lnd1", fmt.Sprintf("payinvoice --force %s", payReq))
	if err != nil {
		log.Fatalf("[!] Payment failed: %v", err)
	}

	fmt.Println("\n=======================================================")
	fmt.Println("[+] Payment Successful!")
	fmt.Println(out)
	fmt.Println("=======================================================")
}
