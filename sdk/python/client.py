"""
client.py — KuberBolt Discovery Scout (bootstrap phase).

Connects to the Go daemon on localhost:50051 via an insecure gRPC channel
and hands over two hardcoded dummy peer endpoints.  The daemon logs them
and returns an acknowledgement.

No Nostr relay integration, no real peer discovery — that comes later.
"""

import grpc

# Generated stubs — produced by protoc from discovery.proto
import discovery_pb2 as pb
import discovery_pb2_grpc as pb_grpc


# ── Hardcoded dummy peer endpoints (placeholder) ────────────────────────────
# In a later phase these will come from Nostr relay discovery.
PEER_A_ENDPOINT = "192.168.1.10:8001"
PEER_B_ENDPOINT = "10.0.0.5:9002"

# ── Daemon address (bootstrap: localhost, insecure) ─────────────────────────
DAEMON_ADDR = "localhost:50051"


def main() -> None:
    """Send the dummy peer endpoints to the Go daemon and print the response."""

    # Insecure channel — no TLS for this bootstrap phase.
    channel = grpc.insecure_channel(DAEMON_ADDR)
    stub = pb_grpc.NodeManagerStub(channel)

    request = pb.PeerHandoverRequest(
        peer_a_endpoint=PEER_A_ENDPOINT,
        peer_b_endpoint=PEER_B_ENDPOINT,
    )

    print(f"[Scout] Sending peers to daemon at {DAEMON_ADDR}")
    print(f"  Peer A: {PEER_A_ENDPOINT}")
    print(f"  Peer B: {PEER_B_ENDPOINT}")

    try:
        response: pb.PeerHandoverResponse = stub.HandoverPeers(request)
        print(f"[Scout] Response — success: {response.success}")
        print(f"[Scout] Response — message: {response.message}")
    except grpc.RpcError as e:
        print(f"[Scout] gRPC error: {e.code()} — {e.details()}")


if __name__ == "__main__":
    main()
