package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"os"
	"os/signal"
	"syscall"

	"github.com/kuberbolt/financial-pod/internal/config"
	"github.com/kuberbolt/financial-pod/internal/gateway"
	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
)

func main() {
	cfgPath  := flag.String("config", "", "Path to config.yaml (overrides default location)")
	agentName := flag.String("name", "", "Agent name (used to locate default config directory)")
	initMode  := flag.Bool("init", false, "Removed: use `kuberbolt init --name <agent>`")
	flag.Parse()

	zapCfg := zap.NewDevelopmentConfig()
	zapCfg.EncoderConfig.EncodeLevel = zapcore.CapitalColorLevelEncoder
	zapCfg.EncoderConfig.TimeKey = "time"
	zapCfg.EncoderConfig.EncodeTime = zapcore.TimeEncoderOfLayout("15:04:05")
	logger, err := zapCfg.Build()
	if err != nil {
		log.Fatalf("failed to build logger: %v", err)
	}
	defer logger.Sync()

	// Key generation is owned by the Python SDK; the pod only loads identity.json.
	if *initMode {
		fmt.Fprintln(os.Stderr, "error: --init was removed; run `kuberbolt init --name <agent>` (Python SDK) to create the config and identity")
		os.Exit(1)
	}

	// Load config.
	var cfg *config.Config
	if *cfgPath != "" {
		cfg, err = config.LoadFromFile(*cfgPath)
	} else if *agentName != "" {
		cfg, err = config.LoadFromDefaultLocation(*agentName)
	} else {
		fmt.Fprintln(os.Stderr, "error: provide --config <path> or --name <agent>")
		os.Exit(1)
	}
	if err != nil {
		logger.Fatal("failed to load config", zap.Error(err))
	}

	// Root context wired to OS signals.
	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()

	// Build and start the Financial Pod server.
	fp, err := gateway.NewServer(ctx, cfg, logger)
	if err != nil {
		logger.Fatal("failed to build Financial Pod", zap.Error(err))
	}

	logger.Info("starting Financial Pod",
		zap.String("agent", cfg.Agent.Name),
		zap.Int("grpc_port", cfg.Network.GRPCPort),
	)

	if err := fp.Start(ctx); err != nil {
		logger.Fatal("Financial Pod start failed", zap.Error(err))
	}

	// Block until SIGINT/SIGTERM.
	<-ctx.Done()
	logger.Info("shutdown signal received, stopping gracefully…")

	stopCtx, stopCancel := context.WithTimeout(context.Background(), 30*1e9) // 30 s
	defer stopCancel()
	if err := fp.Stop(stopCtx); err != nil {
		logger.Error("error during shutdown", zap.Error(err))
	}
	logger.Info("shutdown complete")
}