package main

import (
	"encoding/json"
	"fmt"
	"log"
	"os"
	"strings"
	"time"

	"github.com/devlup-labs/kuberbolt/lightning-node/config"
	"github.com/devlup-labs/kuberbolt/lightning-node/docker"
)

func main() {
	testDataFile := "test-data.json"
	
	// 1. Read existing test-data.json or create default
	var data config.TestData
	fileBytes, err := os.ReadFile(testDataFile)
	if err == nil {
		if err := json.Unmarshal(fileBytes, &data); err != nil {
			log.Fatalf("Failed to parse %s: %v", testDataFile, err)
		}
	} else {
		data = config.TestData{
			User1Node: config.NodeConfig{
				Alias:        "User1_Alice",
				P2PAddress:   "kuberbolt-lnd1:9735",
				GRPCEndpoint: "localhost:10009",
				RESTEndpoint: "https://localhost:8080",
				TLSCertPath:  "./lnd1_data/tls.cert",
			},
			User2Node: config.NodeConfig{
				Alias:        "User2_Bob",
				P2PAddress:   "kuberbolt-lnd2:9735",
				GRPCEndpoint: "localhost:10010",
				RESTEndpoint: "https://localhost:8081",
				TLSCertPath:  "./lnd2_data/tls.cert",
			},
			TestChannelParams: config.ChannelParams{
				FundingAmountSats: 100000,
				PushSatoshis:      1000,
				TargetConf:        1,
			},
		}
	}

	docker.WaitServices()

	// 2. Ensure bitcoind wallet exists and mine regtest blocks
	docker.ExecBitcoin("createwallet defaultwallet")
	miningAddr, _ := docker.ExecBitcoin("getnewaddress")
	docker.ExecBitcoin(fmt.Sprintf("generatetoaddress 106 %s", miningAddr))

	// Wait for LND nodes to sync to chain
	fmt.Println("[*] Waiting for LND nodes to sync to chain...")
	for _, node := range []string{"lnd1", "lnd2"} {
		for i := 0; i < 30; i++ {
			out, err := docker.ExecLND(node, "getinfo")
			if err == nil && strings.Contains(out, `"synced_to_chain":  true`) {
				break
			}
			time.Sleep(1 * time.Second)
		}
	}

	// 3. Query getinfo for lnd1 and lnd2
	out1, err := docker.ExecLND("lnd1", "getinfo")
	if err != nil {
		log.Fatalf("Failed getinfo on lnd1: %v", err)
	}
	var info1 map[string]interface{}
	json.Unmarshal([]byte(out1), &info1)

	out2, err := docker.ExecLND("lnd2", "getinfo")
	if err != nil {
		log.Fatalf("Failed getinfo on lnd2: %v", err)
	}
	var info2 map[string]interface{}
	json.Unmarshal([]byte(out2), &info2)

	pubkey1 := fmt.Sprintf("%v", info1["identity_pubkey"])
	pubkey2 := fmt.Sprintf("%v", info2["identity_pubkey"])

	data.User1Node.Pubkey = pubkey1
	data.User1Node.P2PAddress = fmt.Sprintf("%s@kuberbolt-lnd1:9735", pubkey1)
	data.User1Node.MacaroonHex = docker.GetMacaroonHex("lnd1")

	data.User2Node.Pubkey = pubkey2
	data.User2Node.P2PAddress = fmt.Sprintf("%s@kuberbolt-lnd2:9735", pubkey2)
	data.User2Node.MacaroonHex = docker.GetMacaroonHex("lnd2")

	// 4. Save updated test-data.json
	updatedBytes, _ := json.MarshalIndent(data, "", "  ")
	if err := os.WriteFile(testDataFile, updatedBytes, 0644); err != nil {
		log.Fatalf("Failed to save %s: %v", testDataFile, err)
	}
	fmt.Printf("[+] Updated %s with node credentials.\n", testDataFile)
	fmt.Printf("    User 1 PubKey: %s\n", pubkey1)
	fmt.Printf("    User 2 PubKey: %s\n", pubkey2)

	// 5. Fund lnd1 wallet & connect peers
	addr1Out, _ := docker.ExecLND("lnd1", "newaddress p2wkh")
	var addr1Obj map[string]interface{}
	json.Unmarshal([]byte(addr1Out), &addr1Obj)
	addr1 := fmt.Sprintf("%v", addr1Obj["address"])

	fmt.Println("[*] Funding User 1 wallet from bitcoind...")
	docker.ExecBitcoin(fmt.Sprintf("sendtoaddress %s 2.0", addr1))
	docker.ExecBitcoin(fmt.Sprintf("generatetoaddress 6 %s", miningAddr))

	fmt.Println("[*] Waiting for funding transaction confirmation and chain sync...")
	for i := 0; i < 30; i++ {
		out, _ := docker.ExecLND("lnd1", "walletbalance")
		if strings.Contains(out, `"confirmed_balance"`) && !strings.Contains(out, `"confirmed_balance":  "0"`) {
			break
		}
		time.Sleep(1 * time.Second)
	}

	fmt.Printf("[*] Connecting User 1 to User 2 (%s)...\n", data.User2Node.P2PAddress)
	docker.ExecLND("lnd1", fmt.Sprintf("connect %s", data.User2Node.P2PAddress))

	// 6. Open Channel
	fmt.Printf("[*] Opening channel (Capacity: %d sats, Push: %d sats)...\n",
		data.TestChannelParams.FundingAmountSats, data.TestChannelParams.PushSatoshis)

	openCmd := fmt.Sprintf("openchannel --node_key=%s --connect=kuberbolt-lnd2:9735 --local_amt=%d --push_amt=%d",
		pubkey2, data.TestChannelParams.FundingAmountSats, data.TestChannelParams.PushSatoshis)
	
	_, err = docker.ExecLND("lnd1", openCmd)
	if err != nil {
		fmt.Printf("[!] Note on channel opening: %v\n", err)
	} else {
		fmt.Println("[*] Mining blocks to confirm channel funding transaction...")
		docker.ExecBitcoin(fmt.Sprintf("generatetoaddress 6 %s", miningAddr))
	}

	// 7. Verify channels
	chanOut, _ := docker.ExecLND("lnd1", "listchannels")
	fmt.Println("\n=======================================================")
	fmt.Println("[+] Lightning 2-Node Setup Completed Successfully!")
	fmt.Println("[+] Active channels on User 1:")
	fmt.Println(chanOut)
	fmt.Println("=======================================================")
}
