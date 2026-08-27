import os
import sys
import time
import hashlib
import argparse
from lndgrpc import LNDClient

def test_htlc():
    parser = argparse.ArgumentParser(description="Test LND HTLC Hold Invoices")
    parser.add_argument('--bob-host', default="127.0.0.1:10002", help="Bob (Provider) LND gRPC")
    parser.add_argument('--bob-tls', required=True, help="Bob tls.cert")
    parser.add_argument('--bob-macaroon', required=True, help="Bob admin.macaroon")
    
    parser.add_argument('--alice-host', default="127.0.0.1:10001", help="Alice (Client) LND gRPC")
    parser.add_argument('--alice-tls', required=True, help="Alice tls.cert")
    parser.add_argument('--alice-macaroon', required=True, help="Alice admin.macaroon")
    args = parser.parse_args()

    print("==================================================")
    print(" KUBERBOLT PYTHON HTLC DEMO")
    print("==================================================")

    # 1. Connect to Bob (Provider)
    print("\n[1] Connecting to Bob's LND node...")
    try:
        bob_client = LNDClient(
            args.bob_host, 
            macaroon_filepath=args.bob_macaroon, 
            cert_filepath=args.bob_tls
        )
        bob_info = bob_client.get_info()
        print(f"    -> Connected to Bob: {bob_info.alias}")
    except Exception as e:
        print(f"    -> Failed to connect to Bob: {e}")
        return

    # 2. Connect to Alice (Client)
    print("\n[2] Connecting to Alice's LND node...")
    try:
        alice_client = LNDClient(
            args.alice_host, 
            macaroon_filepath=args.alice_macaroon, 
            cert_filepath=args.alice_tls
        )
        alice_info = alice_client.get_info()
        print(f"    -> Connected to Alice: {alice_info.alias}")
    except Exception as e:
        print(f"    -> Failed to connect to Alice: {e}")
        return

    # 3. Bob creates Hold Invoice
    print("\n[3] Bob is creating a Hold Invoice...")
    preimage = b"secret_preimage_for_the_ai_job__" # 32 bytes
    rhash = hashlib.sha256(preimage).digest()
    print(f"    Preimage: {preimage.hex()}")
    print(f"    Hash: {rhash.hex()}")

    try:
        hold_invoice = bob_client.add_hold_invoice(
            memo="AI Compute Job",
            hash=rhash,
            value_msat=50000
        )
        pay_req = hold_invoice.payment_request
        print(f"    Invoice Created: {pay_req}")
    except Exception as e:
        print(f"    -> Failed to create hold invoice. Are you using lnd-grpc-client >= 0.2.0? {e}")
        return

    # 4. Alice pays the invoice (Locked state)
    print("\n[4] Alice is paying the Hold Invoice (HTLC will lock)...")
    try:
        # We trigger the payment. This will block until settled or failed in some clients, 
        # so we run it asynchronously or wait for it.
        print("    -> Alice is sending payment (this locks the funds on the Lightning Network!)")
        
        # Note: in a real async environment we stream the payment status. 
        # For demo purposes, we will trigger it and immediately check Bob's node.
        # In lndgrpc, pay_invoice is synchronous, so it would hang here if it's a hold invoice.
        # So we skip the actual blocking call in this basic demo script and just explain the concept,
        # or we could use the async client.
        print("    -> [SKIPPED BLOCKING CALL IN SCRIPT: In real app, Alice streams SendPaymentV2]")
    except Exception as e:
        pass

    # 5. Bob checks the invoice
    print("\n[5] Bob checks if the HTLC is locked (ACCEPTED state)...")
    try:
        invoice_status = bob_client.lookup_invoice(r_hash=rhash)
        # 0=OPEN, 1=SETTLED, 2=CANCELED, 3=ACCEPTED
        state_str = ["OPEN", "SETTLED", "CANCELED", "ACCEPTED"][invoice_status.state]
        print(f"    Bob sees Invoice State as: {state_str}")
    except Exception as e:
        print(f"    -> Lookup failed: {e}")

    print("\n[6] Bob completes the AI job and reveals the preimage to settle the invoice...")
    try:
        bob_client.settle_invoice(preimage=preimage)
        print("    Bob successfully settled the invoice and claimed the funds!")
    except Exception as e:
        print(f"    -> Settle failed: {e}")

    print("\n==================================================")
    print(" DEMO COMPLETE")
    print("==================================================")

if __name__ == "__main__":
    test_htlc()
