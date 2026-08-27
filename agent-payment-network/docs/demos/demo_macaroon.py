import os
import sys
import json
import codecs
import requests
import urllib3
import argparse

# Suppress insecure request warnings for self-signed certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_macaroon_header(macaroon_path):
    with open(macaroon_path, 'rb') as f:
        macaroon_bytes = f.read()
    return codecs.encode(macaroon_bytes, 'hex').decode('utf-8')

def test_macaroon():
    parser = argparse.ArgumentParser(description="Test LND Macaroon Access via REST")
    parser.add_argument('--rest-host', default="https://127.0.0.1:8080", help="LND REST Host")
    parser.add_argument('--tls', required=True, help="Path to tls.cert")
    parser.add_argument('--macaroon', required=True, help="Path to admin.macaroon")
    args = parser.parse_args()

    print("==================================================")
    print(" KUBERBOLT PYTHON MACAROON DEMO (REST API)")
    print("==================================================")

    url = f"{args.rest_host}/v1/getinfo"
    tls_cert = args.tls

    print("\n[1] Attempting to connect WITHOUT a Macaroon...")
    try:
        response = requests.get(url, verify=tls_cert, timeout=5)
        if response.status_code == 200:
            print("    -> ERROR: Wait, it succeeded without a macaroon? That shouldn't happen!")
        else:
            print(f"    -> BLOCKED (Expected): {response.status_code} {response.text}")
            print("    -> The Gatekeeper correctly rejected us for lacking the Macaroon token.")
    except Exception as e:
        print(f"    -> Connection Failed: {e}")

    print("\n[2] Attempting to connect WITH the Admin Macaroon...")
    try:
        macaroon_hex = get_macaroon_header(args.macaroon)
        headers = {'Grpc-Metadata-macaroon': macaroon_hex}
        
        response = requests.get(url, headers=headers, verify=tls_cert, timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"    -> SUCCESS! Connected to Node: {data.get('alias')} (Pubkey: {data.get('identity_pubkey')})")
            print("    -> The Gatekeeper ALLOWED access because the Macaroon token was valid!")
        else:
            print(f"    -> FAILED unexpectedly: {response.status_code} {response.text}")
    except Exception as e:
        print(f"    -> Request failed: {e}")

    print("\n==================================================")
    print(" MACAROON DEMO COMPLETE")
    print("==================================================")

if __name__ == "__main__":
    test_macaroon()
