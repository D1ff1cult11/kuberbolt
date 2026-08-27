#!/usr/bin/env bash
# Restore LND credentials from encrypted backup
# Usage: set LND_CONTAINER and provide path to encrypted archive.

set -euo pipefail

LND_CONTAINER=${LND_CONTAINER:-kuberbolt-lnd1}
ENC_ARCHIVE=${1:-}

if [ -z "$ENC_ARCHIVE" ]; then
  echo "Usage: $0 /path/to/lnd_backup_<container>_TIMESTAMP.tar.enc" >&2
  exit 1
fi

read -s -p "Enter passphrase to decrypt backup: " PASSPHRASE
echo

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

echo "Decrypting archive..."
openssl enc -d -aes-256-cbc -pbkdf2 -iter 100000 -pass pass:"$PASSPHRASE" -in "$ENC_ARCHIVE" -out "$TMPDIR/archive.tar"

echo "Extracting..."
tar -C "$TMPDIR" -xf "$TMPDIR/archive.tar"

for f in "$TMPDIR"/*; do
  name=$(basename "$f")
  # decide target inside container
  case "$name" in
    tls.cert)
      target="/root/.lnd/tls.cert" ;;
    admin.macaroon)
      target="/root/.lnd/data/chain/bitcoin/regtest/admin.macaroon" ;;
    graph.db)
      target="/root/.lnd/data/graph.db" ;;
    *)
      echo "Skipping unknown file $name" ; continue ;;
  esac
  echo "Copying $name -> $LND_CONTAINER:$target"
  docker cp "$f" "$LND_CONTAINER":"$target"
done

echo "Restore completed. Restart the LND container to pick up restored files."
