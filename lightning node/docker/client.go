package docker

import (
	"fmt"
	"os/exec"
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
