// Package main — KuberBolt Discovery Daemon (bootstrap phase).
//
// This is the Go "engine" that runs as an independent gRPC server on
// localhost:50051.  It receives peer endpoint pairs from the Python SDK
// ("scout") via the NodeManager.HandoverPeers RPC, logs them, and returns
// a success acknowledgement.
//
// No P2P networking, relay integration, or persistent storage yet — this
// is a minimal receive-and-log skeleton.
package main

import (
	"context"
	"fmt"
	"log"
	"net"

	pb "github.com/kuberbolt/agent-pod/daemon/internal/pb"
	"google.golang.org/grpc"
)

const (
	// listenAddr is the address the gRPC server binds to.
	// Hardcoded for the bootstrap phase; will move to config later.
	listenAddr = ":50051"
)

// server implements the generated pb.NodeManagerServer interface.
type server struct {
	// Embed the "unimplemented" struct so we satisfy the interface even if
	// new RPCs are added to the proto later (forward-compatible).
	pb.UnimplementedNodeManagerServer
}

// HandoverPeers receives two peer endpoints from the Python scout,
// logs them, and returns an acknowledgement.
func (s *server) HandoverPeers(
	ctx context.Context,
	req *pb.PeerHandoverRequest,
) (*pb.PeerHandoverResponse, error) {

	peerA := req.GetPeerAEndpoint()
	peerB := req.GetPeerBEndpoint()

	// ── Log the received endpoints ──────────────────────────────────────
	log.Printf("[HandoverPeers] Received peer endpoints:")
	log.Printf("  Peer A: %s", peerA)
	log.Printf("  Peer B: %s", peerB)

	// TODO: Further processing — route table update, P2P dial, relay
	//       fan-out, etc.  This is where the real engine logic will go.

	msg := fmt.Sprintf("Acknowledged peers: A=%s, B=%s", peerA, peerB)
	return &pb.PeerHandoverResponse{
		Success: true,
		Message: msg,
	}, nil
}

func main() {
	// ── TCP listener ────────────────────────────────────────────────────
	lis, err := net.Listen("tcp", listenAddr)
	if err != nil {
		log.Fatalf("Failed to listen on %s: %v", listenAddr, err)
	}

	// ── gRPC server (insecure — no TLS for this bootstrap phase) ───────
	grpcServer := grpc.NewServer()
	pb.RegisterNodeManagerServer(grpcServer, &server{})

	log.Printf("Discovery daemon listening on %s (insecure)", listenAddr)

	if err := grpcServer.Serve(lis); err != nil {
		log.Fatalf("gRPC server crashed: %v", err)
	}
}
