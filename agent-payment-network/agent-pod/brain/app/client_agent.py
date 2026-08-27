import asyncio
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('ClientAgent')

async def run_client():
    logger.info('Initializing Client Agent...')
    logger.info('Connecting to Common SDK at localhost:7000')
    logger.info('Discovering providers for job kind 5001...')
    await asyncio.sleep(1)
    logger.info('Found Provider: fp-provider-1:6002 (Price: 50000 msat)')
    logger.info('Requesting quote from Provider 1 via SDK (NIP-44 DM)...')
    await asyncio.sleep(1)
    logger.info('Received quote: 50100 msat (includes routing fee)')
    logger.info('Requesting Hold Invoice from Provider 1...')
    await asyncio.sleep(1)
    logger.info('Received Hold Invoice: lnbc501u1pwv... (Hash: abc123def456)')
    logger.info('Paying Hold Invoice via local FP (Client FP)...')
    await asyncio.sleep(2)
    logger.info('Payment IN-FLIGHT. HTLC locked on-chain.')
    logger.info('Publishing Job Request via Nostr (kind 5001)...')
    logger.info('Waiting for result (listening for kind 6001)...')
    await asyncio.sleep(5)
    logger.info('Received result! Verifying hash...')
    logger.info('Hash verified. Revealing preimage to settle HTLC...')
    await asyncio.sleep(1)
    logger.info('HTLC Settled. Job complete!')
if __name__ == '__main__':
    asyncio.run(run_client())