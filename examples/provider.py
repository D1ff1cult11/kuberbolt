import asyncio
import sys
from pathlib import Path

sdk_path = Path(__file__).resolve().parent.parent / "sdk" / "python"
if str(sdk_path) not in sys.path:
    sys.path.insert(0, str(sdk_path))

from nostr_sdk_wrapper.agent import KuberboltAgent

PROVIDER_NSEC = "39cb7ddad069ccdf2636dad4fa8c12d6658db322eb7061f3834a4e3b068c9d7e"
RELAYS = ["wss://relay.damus.io","wss://nos.lol"]

async def main():
    agent = await KuberboltAgent.from_existing_key(
        privkey_hex=PROVIDER_NSEC,
        identity_path="examples/provider_identity.json",
        relay_urls=RELAYS,
    )
    print("provider pubkey:", agent.pubkey_hex)
    print("provider listening for resolve_endpoint handshakes...")
    await agent.serve_endpoint_requests(host="127.0.0.1", port=9000, poll_interval=2)

if __name__ == "__main__":
    asyncio.run(main())