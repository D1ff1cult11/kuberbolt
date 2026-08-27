LND Peer Deployment (single-node template)
=========================================

This folder contains a minimal docker-compose template and a helper script to run a single LND instance intended for a peer-to-peer setup (one LND per user).

Files
- lnd-single-compose.yml: a single LND service template. It expects environment variables to point to a Bitcoind RPC host and credentials if you use a shared `bitcoind`.
- ../scripts/peer-setup.sh: copy-paste helper script with commands to create wallets, fund, connect peers, open channels and test payments (manual execution required).

How to use (high level)
1. Copy `lnd-single-compose.yml` to each user's machine (or adjust host/vars) and set the environment variables `BITCOIND_HOST`, `BITCOIND_RPC_PORT`, `BITCOIND_RPC_USER`, `BITCOIND_RPC_PASS`, and `LND_ALIAS`.
2. Start LND with `docker-compose -f lnd-single-compose.yml up -d` on each machine.
3. Follow the commands in `../scripts/peer-setup.sh` to create wallets, fund addresses (regtest: mine blocks), exchange pubkeys, connect peers, and open channels.
4. Securely back up seeds and macaroons; do not expose admin macaroons publicly.

Security
- Prefer VPN (WireGuard/Tailscale) or Tor for peer connectivity rather than exposing ports publicly.
- Restrict access to gRPC/REST ports and protect macaroons/TLS certificates.

Backup & Restore
- `scripts/backup_lnd_creds.sh`: export LND's `tls.cert`, `admin.macaroon`, and `graph.db`, pack and encrypt them with a passphrase into `backups/`.
- `scripts/restore_lnd_creds.sh`: decrypt and restore files into a running LND container (restart LND after restore).

Important: Keep backups and passphrases offline and encrypted. Do not store macaroons or seed phrases in public or insecure locations.

















Aug 19th work---->
Summary

Task Completed: Implemented a peer-to-peer regtest Lightning workflow, added helper templates/scripts, automated peer/channel setup, and added encrypted backup + restore for LND credentials. You tested a payment end-to-end and confirmed success.
What I did (detailed)

Design & decision: Chose a peer-to-peer deployment (one LND per user) so two machines can run independent LND instances and open channels directly between them (no central custodian).
Compose/template work: Added a single-LND compose template for per-user deployment so each user can run one LND instance configured to the shared Bitcoind or local bitcoind.
Helper scripts: Created shell helpers to:
create/load wallets, fund regtest addresses, connect peers, open channels, and pay invoices (manual helper).
automate connecting nodes and opening a channel with minimal steps (scripted helper).
Backups: Implemented an encrypted backup script to export and encrypt tls.cert, admin.macaroon, and graph DB; added a restore script to decrypt and copy those files back into a running LND container.
Docs: Updated the deployment README to document usage, security guidance, and backup/restore instructions.
Testing & debugging: Walked through regtest wallet creation/loading, mining blocks, funding, connecting peers, opening channel, and sending a Lightning payment; resolved common pitfalls (missing bitcoind wallet,generatetoaddress, lncli --network=regtest usage, macaroon/tls paths).
Files added or updated

Template: lightning node/templates/lnd-single-compose.yml — single LND service compose template.
Script (manual setup): lightning node/scripts/peer-setup.sh — sequence of lncli/bitcoin-cli commands for manual setup and testing.
Script (automation): lightning node/scripts/auto-open-channel.sh — automates connect → openchannel → mine confirmations → wait-for-active.
Backup script: lightning node/scripts/backup_lnd_creds.sh — collects tls.cert, admin.macaroon, graph.db, tars and AES-256-CBC encrypts to backups/.
Restore script: lightning node/scripts/restore_lnd_creds.sh — decrypts archived backup and copies files into a running LND container (restart LND after restore).
Docs: lightning node/templates/README-LND-peer.md — updated with Backup & Restore section and security notes.
(You can open the files directly: README-LND-peer.md, backup_lnd_creds.sh, restore_lnd_creds.sh)

Commands I ran or recommended

Typical bring-up for the compose stack (run locally where Docker is installed):
Commands I ran or recommended

Typical bring-up for the compose stack (run locally where Docker is installed):
cd "lightning node"
docker-compose up -d
# mine 101 regtest blocks (inside bitcoind container)
docker exec -i kuberbolt-bitcoind bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpassword generatetoaddress 101 bcrt1q...address
Example: run the auto open-channel script (make executable first):
chmod +x lightning\ node/scripts/auto-open-channel.sh
LIGHTNING_DIR="lightning node" && ./lightning\ node/scripts/auto-open-channel.sh

Backup example:
# from repo root
chmod +x lightning\ node/scripts/backup_lnd_creds.sh
LND_CONTAINER=kuberbolt-lnd1 BACKUP_DIR=~/lnd_backups lightning\ node/scripts/backup_lnd_creds.sh
Restore example:
chmod +x lightning\ node/scripts/restore_lnd_creds.sh
LND_CONTAINER=kuberbolt-lnd1 lightning\ node/scripts/restore_lnd_creds.sh /path/to/lnd_backup_kuberbolt-lnd1_2026-08-20.tar.enc
# restart the LND container after restore
docker restart kuberbolt-lnd1


Issues encountered & fixes

Missing bitcoind wallet: bitcoin-cli sendtoaddress failed until a regtest wallet was created/loaded. Fix: createwallet / loadwallet inside the bitcoind container.
generate -> generatetoaddress: Used generatetoaddress for mining on modern bitcoind; updated commands accordingly.
lncli macaroon/tls path warnings: Use lncli --network=regtest when interacting with regtest LND to find correct macaroon/tls paths.
Wallet already exists / unlock issues: LND may skip WalletUnlocker if wallet already created; handle by checking wallet state before calling create/unlock.
Local agent limitation: Attempted to run compose from the agent environment (no docker-compose); you performed those steps locally — that’s expected.

Security notes

Backups are encrypted with openssl enc -aes-256-cbc -pbkdf2 — keep passphrases offline and separate from the backup files.
Do not expose admin macaroons or TLS certs publicly. Use VPN/Tailscale/WireGuard or Tor for peer connectivity across machines.
After restore, ensure file permissions and ownership inside the container are correct (restart container so LND picks up restored assets).

Next recommended steps

Parameterize and harden scripts:
Add CLI flags and validation to backup_lnd_creds.sh and restore_lnd_creds.sh.
Add checks to confirm files exist before encrypting/restoring.
Add an automated verification step after restore to ensure LND recognizes restored macaroon/tls/graph.db.
Consider automating secure offsite backup (e.g., encrypted upload to an S3-compatible bucket or an air-gapped USB with multiple copies).
Harden network access: lock admin ports, run LND RPC behind VPN, and rotate macaroons periodically.