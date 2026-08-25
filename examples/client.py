import asyncio
import sys
from pathlib import Path

sdk_path = Path(__file__).resolve().parent.parent / "sdk" / "python"
if str(sdk_path) not in sys.path:
    sys.path.insert(0, str(sdk_path))

from nostr_sdk_wrapper.agent import KuberboltAgent

CLIENT_NSEC = "1fd94547e03a4f08a89378858275ff32b8fac3d29f2ebd5710e4ddef18b94382"
RELAYS = ["wss://relay.damus.io", "wss://nos.lol"]
PROVIDER_PUBKEY = "740bb0bc7f57114237ca5c872bdd0ab4261a9601b7aefdbed638b08b2c7c4afa"  # the provider's public key

async def main():
    agent = await KuberboltAgent.from_existing_key(
        privkey_hex=CLIENT_NSEC,
        identity_path="examples/client_identity.json",
        relay_urls=RELAYS,
    )
    print("sending handshake to provider:", PROVIDER_PUBKEY)
    await agent.send_handshake(PROVIDER_PUBKEY, {"action": "resolve_endpoint", "job_id": "test-1"})
    reply = await agent.fetch_handshake_replies(timeout_secs=30)
    print("Got reply:", reply)

if __name__ == "__main__":
    asyncio.run(main())