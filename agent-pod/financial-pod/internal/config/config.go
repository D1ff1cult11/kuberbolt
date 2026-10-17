package config

import (
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/kuberbolt/financial-pod/internal/budget"
	"gopkg.in/yaml.v3"
)

// Roles accepted in agent.role (same values as the Python SDK).
const (
	RoleClient   = "client"
	RoleMerchant = "merchant"
)

// Config is the complete agent configuration loaded from config.yaml.
// The schema is shared with the Python SDK; see kuberbolt-config/agent.example.yaml.
type Config struct {
	Agent     AgentConfig     `yaml:"agent"`
	Services  []ServiceConfig `yaml:"services"`
	Network   NetworkConfig   `yaml:"network"`
	Brain     BrainConfig     `yaml:"brain"`
	Lightning LightningConfig `yaml:"lightning"`
	Budget    budget.Config   `yaml:"budget"`
	Logging   LoggingConfig   `yaml:"logging"`

	// Dir is the directory of the loaded config file. Relative paths
	// (identity_file, ledger_path) resolve against it.
	Dir string `yaml:"-"`
	// NostrSecretKeyHex is loaded from agent.identity_file and never written to config.yaml.
	NostrSecretKeyHex string `yaml:"-"`
}

type AgentConfig struct {
	Name             string `yaml:"name"`
	Role             string `yaml:"role"`
	IdentityFile     string `yaml:"identity_file"`
	LedgerPath       string `yaml:"ledger_path"`
	DisplayName      string `yaml:"display_name"`
	About            string `yaml:"about"`
	PictureURL       string `yaml:"picture_url"`
	LightningAddress string `yaml:"lightning_address"`
}

type ServiceConfig struct {
	Name        string `yaml:"name"`
	Category    string `yaml:"category"`
	Kind        int    `yaml:"kind"`
	Description string `yaml:"description"`
	PriceMSat   int64  `yaml:"price_msat"`
	PriceUnit   string `yaml:"price_unit"`
	TimeoutSec  int    `yaml:"timeout_sec"`
}

type NetworkConfig struct {
	GRPCPort            int      `yaml:"grpc_port"`
	PublicHost          string   `yaml:"public_host"`
	PodAddr             string   `yaml:"pod_addr"`
	NostrRelays         []string `yaml:"nostr_relays"`
	RelayConnectWaitSec int      `yaml:"relay_connect_wait_sec"`
	HandshakeTimeoutSec int      `yaml:"handshake_timeout_sec"`
	DiscoveryTimeoutSec int      `yaml:"discovery_timeout_sec"`
}

// BrainConfig describes the private compute service co-located with this
// Financial Pod. It is deliberately separate from the public gRPC endpoint.
type BrainConfig struct {
	URL        string `yaml:"url"`
	ListenHost string `yaml:"listen_host"`
	ListenPort int    `yaml:"listen_port"`
	LLMModel   string `yaml:"llm_model"`
}

type LightningConfig struct {
	Network      string `yaml:"network"` // "regtest", "testnet", "mainnet"
	LNDHost      string `yaml:"lnd_host"`
	LNDGRPCPort  int    `yaml:"lnd_grpc_port"`
	TLSCertPath  string `yaml:"tls_cert_path"`
	MacaroonPath string `yaml:"macaroon_path"`
}

type LoggingConfig struct {
	Level  string `yaml:"level"`
	Format string `yaml:"format"`
}

// DefaultDir returns the agent's config directory: $KUBERBOLT_HOME/<name>,
// falling back to ~/.kuberbolt/<name> (same rule as the Python SDK).
func DefaultDir(agentName string) (string, error) {
	if home := os.Getenv("KUBERBOLT_HOME"); home != "" {
		return filepath.Join(home, agentName), nil
	}
	userHome, err := os.UserHomeDir()
	if err != nil {
		return "", fmt.Errorf("config: KUBERBOLT_HOME not set and home directory unknown: %w", err)
	}
	return filepath.Join(userHome, ".kuberbolt", agentName), nil
}

// LoadFromFile reads config.yaml, validates the fields the pod needs, and
// loads the Nostr secret key from agent.identity_file.
func LoadFromFile(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("config: read %q: %w", path, err)
	}
	cfg := &Config{}
	if err := yaml.Unmarshal(data, cfg); err != nil {
		return nil, fmt.Errorf("config: parse %q: %w", path, err)
	}
	abs, err := filepath.Abs(path)
	if err != nil {
		return nil, fmt.Errorf("config: resolve %q: %w", path, err)
	}
	cfg.Dir = filepath.Dir(abs)
	if err := cfg.Validate(); err != nil {
		return nil, fmt.Errorf("config: %s: %w", path, err)
	}
	cfg.NostrSecretKeyHex, err = loadSecretKeyHex(cfg.ResolvePath(cfg.Agent.IdentityFile))
	if err != nil {
		return nil, err
	}
	return cfg, nil
}

// LoadFromDefaultLocation loads config.yaml from DefaultDir(agentName).
func LoadFromDefaultLocation(agentName string) (*Config, error) {
	dir, err := DefaultDir(agentName)
	if err != nil {
		return nil, err
	}
	return LoadFromFile(filepath.Join(dir, "config.yaml"))
}

// ResolvePath returns p unchanged if absolute, otherwise joined to cfg.Dir.
func (cfg *Config) ResolvePath(p string) string {
	if filepath.IsAbs(p) {
		return p
	}
	return filepath.Join(cfg.Dir, p)
}

// Validate returns an error naming every missing setting the pod needs to run.
// Merchants need a brain and a priced service; clients need budget limits.
func (cfg *Config) Validate() error {
	var missing []string
	need := func(ok bool, field string) {
		if !ok {
			missing = append(missing, field)
		}
	}
	need(cfg.Agent.Name != "", "agent.name")
	need(cfg.Agent.IdentityFile != "", "agent.identity_file")
	need(cfg.Agent.LedgerPath != "", "agent.ledger_path")
	need(cfg.Network.GRPCPort > 0, "network.grpc_port")
	need(cfg.Lightning.LNDHost != "", "lightning.lnd_host")
	need(cfg.Lightning.LNDGRPCPort > 0, "lightning.lnd_grpc_port")
	need(cfg.Lightning.TLSCertPath != "", "lightning.tls_cert_path")
	need(cfg.Lightning.MacaroonPath != "", "lightning.macaroon_path")

	switch cfg.Agent.Role {
	case RoleMerchant:
		need(cfg.Brain.URL != "", "brain.url")
		need(len(cfg.Services) > 0, "services")
		if len(cfg.Services) > 0 {
			need(cfg.Services[0].PriceMSat > 0, "services[0].price_msat")
		}
	case RoleClient:
		need(cfg.Budget.DailyLimitMSat > 0, "budget.daily_limit_msat")
		need(cfg.Budget.MonthlyLimitMSat > 0, "budget.monthly_limit_msat")
	default:
		missing = append(missing, fmt.Sprintf("agent.role (%q or %q, got %q)", RoleClient, RoleMerchant, cfg.Agent.Role))
	}

	if len(missing) > 0 {
		return fmt.Errorf("missing or invalid required setting(s): %s", strings.Join(missing, ", "))
	}
	return nil
}

// loadSecretKeyHex reads secret_key_hex from an identity.json written by the
// Python SDK (`kuberbolt init`). The pod never generates keys itself.
func loadSecretKeyHex(path string) (string, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return "", fmt.Errorf("config: read identity_file %q (create it with `kuberbolt init --name <agent>`): %w", path, err)
	}
	var id struct {
		SecretKeyHex string `json:"secret_key_hex"`
	}
	if err := json.Unmarshal(data, &id); err != nil {
		return "", fmt.Errorf("config: parse identity_file %q: %w", path, err)
	}
	if b, err := hex.DecodeString(id.SecretKeyHex); err != nil || len(b) != 32 {
		return "", fmt.Errorf("config: identity_file %q: secret_key_hex must be 64 hex characters", path)
	}
	return id.SecretKeyHex, nil
}

// Save marshals cfg to YAML and writes it to path at mode 0600.
func Save(cfg *Config, path string) error {
	data, err := yaml.Marshal(cfg)
	if err != nil {
		return fmt.Errorf("config: marshal: %w", err)
	}
	if err := os.WriteFile(path, data, 0600); err != nil {
		return fmt.Errorf("config: write %q: %w", path, err)
	}
	return nil
}
