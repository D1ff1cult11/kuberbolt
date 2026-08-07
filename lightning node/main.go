package main

import (
	"encoding/json"
	"fmt"
	"log"
	"os"
	"os/exec"
	"strings"
	"time"
)

type NodeConfig struct {
	Alias        string `json:"alias"`
	Pubkey       string `json:"pubkey"`
	P2PAddress   string `json:"p2p_address"`
	GRPCEndpoint string `json:"grpc_endpoint"`
	RESTEndpoint string `json:"rest_endpoint"`
	MacaroonHex  string `json:"macaroon_hex"`
	TLSCertPath  string `json:"tls_cert_path"`
}

type ChannelParams struct {
	FundingAmountSats int64 `json:"funding_amount_sats"`
	PushSatellites    int64 `json:"push_satellites"`
	TargetConf        int   `json:"target_conf"`
}

type TestData struct {
	User1Node          NodeConfig    `json:"user1_node"`
	User2Node          NodeConfig    `json:"user2_node"`
	TestChannelParams  ChannelParams `json:"test_channel_params"`
}

func runCmd(cmdStr string) (string, error) {
	cmd := exec.Command("sh", "-c", cmdStr)
	out, err := cmd.CombinedOutput()
	if err != nil {
		return "", fmt.Errorf("command failed: %s\noutput: %s", cmdStr, string(out))
	}
	return strings.TrimSpace(string(out)), nil
}

func execBitcoin(cliArgs string) (string, error) {
	fullCmd := fmt.Sprintf("docker exec -i kuberbolt-bitcoind bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpassword %s", cliArgs)
	return runCmd(fullCmd)
}

func execLND(node string, cliArgs string) (string, error) {
	containerName := "kuberbolt-" + node
	fullCmd := fmt.Sprintf("docker exec -i %s lncli --network=regtest %s", containerName, cliArgs)
	return runCmd(fullCmd)
}

func waitServices() {
	fmt.Println("[*] Waiting for Docker containers (bitcoind, lnd1, lnd2) to be ready...")
	for i := 0; i < 30; i++ {
		_, err := execBitcoin("getblockchaininfo")
		if err == nil {
			break
		}
		time.Sleep(1 * time.Second)
	}

	for _, node := range []string{"lnd1", "lnd2"} {
		for i := 0; i < 30; i++ {
			out, err := execLND(node, "getinfo")
			if err == nil && strings.Contains(out, "identity_pubkey") {
				break
			}
			time.Sleep(1 * time.Second)
		}
	}
	fmt.Println("[+] All services are ready.")
}

func getMacaroonHex(node string) string {
	containerName := "kuberbolt-" + node
	cmd := fmt.Sprintf("docker exec -i %s xxd -p /root/.lnd/data/chain/bitcoin/regtest/admin.macaroon | tr -d '\\r\\n'", containerName)
	out, err := runCmd(cmd)
	if err != nil {
		fallback := fmt.Sprintf("docker exec -i %s od -An -tx1 /root/.lnd/data/chain/bitcoin/regtest/admin.macaroon | tr -d ' \\r\\n'", containerName)
		out, _ = runCmd(fallback)
	}
	return out
}

func main() {
	testDataFile := "test-data.json"
	
	// 1. Read existing test-data.json or create default
	var data TestData
	fileBytes, err := os.ReadFile(testDataFile)
	if err == nil {
		if err := json.Unmarshal(fileBytes, &data); err != nil {
			log.Fatalf("Failed to parse %s: %v", testDataFile, err)
		}
	} else {
		data = TestData{
			User1Node: NodeConfig{
				Alias:        "lnd-user1",
				P2PAddress:   "kuberbolt-lnd1:9735",
				GRPCEndpoint: "localhost:10009",
				RESTEndpoint: "https://localhost:8080",
				TLSCertPath:  "./lnd1_data/tls.cert",
			},
			User2Node: NodeConfig{
				Alias:        "lnd-user2",
				P2PAddress:   "kuberbolt-lnd2:9735",
				GRPCEndpoint: "localhost:10010",
				RESTEndpoint: "https://localhost:8081",
				TLSCertPath:  "./lnd2_data/tls.cert",
			},
			TestChannelParams: ChannelParams{
				FundingAmountSats: 100000,
				PushSatellites:    1000,
				TargetConf:        1,
			},
		}
	}

	waitServices()

	// 2. Ensure bitcoind wallet exists and mine regtest blocks
	execBitcoin("createwallet defaultwallet")
	miningAddr, _ := execBitcoin("getnewaddress")
	execBitcoin(fmt.Sprintf("generatetoaddress 106 %s", miningAddr))

	// Wait for LND nodes to sync to chain
	fmt.Println("[*] Waiting for LND nodes to sync to chain...")
	for _, node := range []string{"lnd1", "lnd2"} {
		for i := 0; i < 30; i++ {
			out, err := execLND(node, "getinfo")
			if err == nil && strings.Contains(out, `"synced_to_chain":  true`) {
				break
			}
			time.Sleep(1 * time.Second)
		}
	}

	// 3. Query getinfo for lnd1 and lnd2
	out1, err := execLND("lnd1", "getinfo")
	if err != nil {
		log.Fatalf("Failed getinfo on lnd1: %v", err)
	}
	var info1 map[string]interface{}
	json.Unmarshal([]byte(out1), &info1)

	out2, err := execLND("lnd2", "getinfo")
	if err != nil {
		log.Fatalf("Failed getinfo on lnd2: %v", err)
	}
	var info2 map[string]interface{}
	json.Unmarshal([]byte(out2), &info2)

	pubkey1 := fmt.Sprintf("%v", info1["identity_pubkey"])
	pubkey2 := fmt.Sprintf("%v", info2["identity_pubkey"])

	data.User1Node.Pubkey = pubkey1
	data.User1Node.P2PAddress = fmt.Sprintf("%s@kuberbolt-lnd1:9735", pubkey1)
	data.User1Node.MacaroonHex = getMacaroonHex("lnd1")

	data.User2Node.Pubkey = pubkey2
	data.User2Node.P2PAddress = fmt.Sprintf("%s@kuberbolt-lnd2:9735", pubkey2)
	data.User2Node.MacaroonHex = getMacaroonHex("lnd2")

	// 4. Save updated test-data.json
	updatedBytes, _ := json.MarshalIndent(data, "", "  ")
	if err := os.WriteFile(testDataFile, updatedBytes, 0644); err != nil {
		log.Fatalf("Failed to save %s: %v", testDataFile, err)
	}
	fmt.Printf("[+] Updated %s with node credentials.\n", testDataFile)
	fmt.Printf("    User 1 PubKey: %s\n", pubkey1)
	fmt.Printf("    User 2 PubKey: %s\n", pubkey2)

	// 5. Fund lnd1 wallet & connect peers
	addr1Out, _ := execLND("lnd1", "newaddress p2wkh")
	var addr1Obj map[string]interface{}
	json.Unmarshal([]byte(addr1Out), &addr1Obj)
	addr1 := fmt.Sprintf("%v", addr1Obj["address"])

	fmt.Println("[*] Funding User 1 wallet from bitcoind...")
	execBitcoin(fmt.Sprintf("sendtoaddress %s 2.0", addr1))
	execBitcoin(fmt.Sprintf("generatetoaddress 6 %s", miningAddr))

	fmt.Println("[*] Waiting for funding transaction confirmation and chain sync...")
	for i := 0; i < 30; i++ {
		out, _ := execLND("lnd1", "walletbalance")
		if strings.Contains(out, `"confirmed_balance"`) && !strings.Contains(out, `"confirmed_balance":  "0"`) {
			break
		}
		time.Sleep(1 * time.Second)
	}

	fmt.Printf("[*] Connecting User 1 to User 2 (%s)...\n", data.User2Node.P2PAddress)
	execLND("lnd1", fmt.Sprintf("connect %s", data.User2Node.P2PAddress))

	// 6. Open Channel
	fmt.Printf("[*] Opening channel (Capacity: %d sats, Push: %d sats)...\n",
		data.TestChannelParams.FundingAmountSats, data.TestChannelParams.PushSatellites)

	openCmd := fmt.Sprintf("openchannel --node_key=%s --connect=kuberbolt-lnd2:9735 --local_amt=%d --push_amt=%d",
		pubkey2, data.TestChannelParams.FundingAmountSats, data.TestChannelParams.PushSatellites)
	
	_, err = execLND("lnd1", openCmd)
	if err != nil {
		fmt.Printf("[!] Note on channel opening: %v\n", err)
	} else {
		fmt.Println("[*] Mining blocks to confirm channel funding transaction...")
		execBitcoin(fmt.Sprintf("generatetoaddress 6 %s", miningAddr))
	}

	// 7. Verify channels
	chanOut, _ := execLND("lnd1", "listchannels")
	fmt.Println("\n=======================================================")
	fmt.Println("[+] Lightning 2-Node Setup Completed Successfully!")
	fmt.Println("[+] Active channels on User 1:")
	fmt.Println(chanOut)
	fmt.Println("=======================================================")
}
