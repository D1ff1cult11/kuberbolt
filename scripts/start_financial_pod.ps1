# Start this agent's financial pod. Its gRPC port comes from network.grpc_port in the config.
# Config: $env:KUBERBOLT_HOME\$env:KUBERBOLT_AGENT\config.yaml (KUBERBOLT_HOME defaults to ~\.kuberbolt).
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

if (-not $env:KUBERBOLT_AGENT) { throw "Set KUBERBOLT_AGENT to the agent name" }
$kbHome = if ($env:KUBERBOLT_HOME) { $env:KUBERBOLT_HOME } else { Join-Path $HOME ".kuberbolt" }
$config = Join-Path (Join-Path $kbHome $env:KUBERBOLT_AGENT) "config.yaml"
if (-not (Test-Path $config)) {
    throw "No config at $config. Run: kuberbolt init --name $($env:KUBERBOLT_AGENT) --role <client|merchant>, then fill in config.yaml."
}

Set-Location (Join-Path $repoRoot "agent-pod\financial-pod")
go run ./cmd/financialpod --config $config
