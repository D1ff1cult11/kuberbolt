package docker

import (
	"encoding/json"
	"fmt"
	"os/exec"
	"strconv"
	"strings"
	"time"
)

func RunCmd(cmdStr string) (string, error) {
	cmd := exec.Command("sh", "-c", cmdStr)
	out, err := cmd.CombinedOutput()
	if err != nil {
		return "", fmt.Errorf("command failed: %s\noutput: %s", cmdStr, string(out))
	}
	return strings.TrimSpace(string(out)), nil
}

func ExecBitcoin(cliArgs string) (string, error) {
	fullCmd := fmt.Sprintf("docker exec -i kuberbolt-bitcoind bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpassword %s", cliArgs)
	return RunCmd(fullCmd)
}

func ExecLND(node string, cliArgs string) (string, error) {
	containerName := "kuberbolt-" + node
	fullCmd := fmt.Sprintf("docker exec -i %s lncli --network=regtest %s", containerName, cliArgs)
	return RunCmd(fullCmd)
}

func WaitServices() {
	fmt.Println("[*] Waiting for Docker containers (bitcoind, lnd1, lnd2) to be ready...")
	for i := 0; i < 30; i++ {
		_, err := ExecBitcoin("getblockchaininfo")
		if err == nil {
			break
		}
		time.Sleep(1 * time.Second)
	}

	for _, node := range []string{"lnd1", "lnd2"} {
		for i := 0; i < 30; i++ {
			out, err := ExecLND(node, "getinfo")
			if err == nil && strings.Contains(out, "identity_pubkey") {
				break
			}
			time.Sleep(1 * time.Second)
		}
	}
	fmt.Println("[+] All services are ready.")
}

func GetMacaroonHex(node string) string {
	containerName := "kuberbolt-" + node
	cmd := fmt.Sprintf("docker exec -i %s xxd -p /root/.lnd/data/chain/bitcoin/regtest/admin.macaroon | tr -d '\\r\\n'", containerName)
	out, err := RunCmd(cmd)
	if err != nil {
		fallback := fmt.Sprintf("docker exec -i %s od -An -tx1 /root/.lnd/data/chain/bitcoin/regtest/admin.macaroon | tr -d ' \\r\\n'", containerName)
		out, _ = RunCmd(fallback)
	}
	return out
}

type DecodedInvoiceInfo struct {
	NumSatoshis int64  `json:"num_satoshis"`
	Destination string `json:"destination"`
	Description string `json:"description"`
	PaymentHash string `json:"payment_hash"`
}

// DecodeInvoice decodes a BOLT11 payment request string using lncli decodepayreq
func DecodeInvoice(node string, payReq string) (*DecodedInvoiceInfo, error) {
	out, err := ExecLND(node, fmt.Sprintf("decodepayreq %s", payReq))
	if err != nil {
		return nil, fmt.Errorf("failed to decode payment request: %w", err)
	}

	var raw map[string]interface{}
	if err := json.Unmarshal([]byte(out), &raw); err != nil {
		return nil, fmt.Errorf("failed to parse decodepayreq JSON: %w", err)
	}

	var satoshis int64
	if numSat, ok := raw["num_satoshis"]; ok {
		switch v := numSat.(type) {
		case string:
			satoshis, _ = strconv.ParseInt(v, 10, 64)
		case float64:
			satoshis = int64(v)
		}
	}

	return &DecodedInvoiceInfo{
		NumSatoshis: satoshis,
		Destination: fmt.Sprintf("%v", raw["destination"]),
		Description: fmt.Sprintf("%v", raw["description"]),
		PaymentHash: fmt.Sprintf("%v", raw["payment_hash"]),
	}, nil
}

// PayInvoiceWithGuardrail checks if invoice amount is within maxPaymentSats before executing payment
func PayInvoiceWithGuardrail(node string, payReq string, maxPaymentSats int64) (string, error) {
	decoded, err := DecodeInvoice(node, payReq)
	if err != nil {
		return "", err
	}

	if decoded.NumSatoshis > maxPaymentSats {
		return "", fmt.Errorf("[GUARDRAIL REJECTED] Payment of %d sats exceeds maximum allowed limit of %d sats",
			decoded.NumSatoshis, maxPaymentSats)
	}

	fmt.Printf("[GUARDRAIL PASSED] Payment of %d sats is within allowed limit of %d sats. Proceeding with payment...\n",
		decoded.NumSatoshis, maxPaymentSats)

	return ExecLND(node, fmt.Sprintf("payinvoice --force %s", payReq))
}

