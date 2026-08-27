#!/usr/bin/env bash
# Backup LND credentials (macaroons + tls cert + wallet db)
# Usage: set LND_CONTAINER and BACKUP_DIR, then run.

set -euo pipefail

LND_CONTAINER=${LND_CONTAINER:-kuberbolt-lnd1}
BACKUP_DIR=${BACKUP_DIR:-./backups}
PASSPHRASE=${LND_BACKUP_PASSPHRASE:-}

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

echo "Exporting files from container $LND_CONTAINER..."
# paths inside container
FILES=("/root/.lnd/tls.cert" "/root/.lnd/data/chain/bitcoin/regtest/admin.macaroon" "/root/.lnd/data/graph.db" )

for f in "${FILES[@]}"; do
  name=$(basename "$f")
  out="$TMPDIR/$name"
  if docker exec "$LND_CONTAINER" test -f "$f"; then
    docker exec "$LND_CONTAINER" cat "$f" > "$out"
    echo "  exported $f -> $out"
  else
    echo "  warning: $f not found in container" >&2
  fi
done

# Ask for passphrase if not provided
if [ -z "$PASSPHRASE" ]; then
  read -s -p "Enter passphrase to encrypt backup: " PASSPHRASE
  echo
  read -s -p "Confirm passphrase: " PASSPHRASE2
  echo
  if [ "$PASSPHRASE" != "$PASSPHRASE2" ]; then
    echo "Passphrases do not match" >&2
    exit 2
  fi
fi

TIMESTAMP=$(date -u +%Y%m%dT%H%M%SZ)
ARCHIVE="$BACKUP_DIR/lnd_backup_${LND_CONTAINER}_${TIMESTAMP}.tar"
ENC_ARCHIVE="$ARCHIVE.enc"

tar -C "$TMPDIR" -cf "$ARCHIVE" .

echo "Encrypting archive to $ENC_ARCHIVE (AES-256-CBC)..."
openssl enc -aes-256-cbc -salt -pbkdf2 -iter 100000 -pass pass:"$PASSPHRASE" -in "$ARCHIVE" -out "$ENC_ARCHIVE"
rm -f "$ARCHIVE"

chmod 600 "$ENC_ARCHIVE"

echo "Backup complete: $ENC_ARCHIVE"
echo "Store the passphrase securely; without it the backup cannot be decrypted."
