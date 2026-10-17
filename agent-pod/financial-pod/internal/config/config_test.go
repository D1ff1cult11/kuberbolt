package config

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

const fixtureSecretHex = "0101010101010101010101010101010101010101010101010101010101010101"

const fixtureConfig = `agent:
  name: alice
  role: client
  identity_file: identity.json
  ledger_path: ledger.db
  display_name: Alice
network:
  grpc_port: 7001
  pod_addr: host.test:7001
  nostr_relays: [wss://relay.test]
  relay_connect_wait_sec: 2
  handshake_timeout_sec: 30
  discovery_timeout_sec: 10
brain:
  llm_model: test-model
lightning:
  network: regtest
  lnd_host: lnd.test
  lnd_grpc_port: 10019
  tls_cert_path: /certs/tls.cert
  macaroon_path: /certs/admin.macaroon
budget:
  daily_limit_msat: 1000
  monthly_limit_msat: 2000
`

func writeFixture(t *testing.T, dir, name, body string) string {
	t.Helper()
	p := filepath.Join(dir, name)
	if err := os.WriteFile(p, []byte(body), 0600); err != nil {
		t.Fatal(err)
	}
	return p
}

func writeIdentity(t *testing.T, dir string) {
	writeFixture(t, dir, "identity.json", `{
  "secret_key_hex": "`+fixtureSecretHex+`",
  "secret_key_bech32": "nsec1test",
  "public_key_hex": "02",
  "public_key_bech32": "npub1test"
}`)
}

func TestLoadResolvesRelativeIdentityFile(t *testing.T) {
	dir := t.TempDir()
	writeIdentity(t, dir)
	cfgPath := writeFixture(t, dir, "config.yaml", fixtureConfig)

	cfg, err := LoadFromFile(cfgPath)
	if err != nil {
		t.Fatalf("LoadFromFile: %v", err)
	}
	if cfg.NostrSecretKeyHex != fixtureSecretHex {
		t.Fatalf("secret key = %q", cfg.NostrSecretKeyHex)
	}
	if got := cfg.ResolvePath(cfg.Agent.LedgerPath); got != filepath.Join(dir, "ledger.db") {
		t.Fatalf("ledger path = %q", got)
	}
	if cfg.Network.PodAddr != "host.test:7001" || cfg.Brain.LLMModel != "test-model" {
		t.Fatalf("new schema fields not parsed: %+v %+v", cfg.Network, cfg.Brain)
	}

	// Save must keep the new fields and must not write the secret key.
	out := filepath.Join(dir, "saved.yaml")
	if err := Save(cfg, out); err != nil {
		t.Fatal(err)
	}
	saved, _ := os.ReadFile(out)
	if strings.Contains(string(saved), fixtureSecretHex) {
		t.Fatal("Save wrote the secret key to config.yaml")
	}
	for _, field := range []string{"identity_file", "pod_addr", "handshake_timeout_sec", "llm_model"} {
		if !strings.Contains(string(saved), field) {
			t.Fatalf("Save dropped %s", field)
		}
	}
}

func TestLoadMissingIdentityFile(t *testing.T) {
	dir := t.TempDir()
	cfgPath := writeFixture(t, dir, "config.yaml", fixtureConfig)

	_, err := LoadFromFile(cfgPath)
	if err == nil || !strings.Contains(err.Error(), "identity_file") || !strings.Contains(err.Error(), "kuberbolt init") {
		t.Fatalf("want identity_file error pointing to kuberbolt init, got %v", err)
	}
}

func TestLoadMissingRequiredField(t *testing.T) {
	dir := t.TempDir()
	writeIdentity(t, dir)
	cfgPath := writeFixture(t, dir, "config.yaml", strings.Replace(fixtureConfig, "grpc_port: 7001", "grpc_port: 0", 1))

	_, err := LoadFromFile(cfgPath)
	if err == nil || !strings.Contains(err.Error(), "network.grpc_port") {
		t.Fatalf("want network.grpc_port error, got %v", err)
	}
}

func TestValidateMerchantNeedsBrainAndService(t *testing.T) {
	cfg := &Config{}
	cfg.Agent = AgentConfig{Name: "bob", Role: RoleMerchant, IdentityFile: "identity.json", LedgerPath: "ledger.db"}
	err := cfg.Validate()
	if err == nil || !strings.Contains(err.Error(), "brain.url") || !strings.Contains(err.Error(), "services") {
		t.Fatalf("want brain.url and services errors, got %v", err)
	}
}

func TestDefaultDirHonorsKuberboltHome(t *testing.T) {
	home := t.TempDir()
	t.Setenv("KUBERBOLT_HOME", home)
	dir, err := DefaultDir("alice")
	if err != nil || dir != filepath.Join(home, "alice") {
		t.Fatalf("DefaultDir = %q, %v", dir, err)
	}
}
