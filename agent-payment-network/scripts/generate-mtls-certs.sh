#!/bin/bash
set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

CERTS_DIR="$(dirname "$0")/../certs"

echo -e "${BLUE}╔════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║    KUBERBOLT mTLS CERT GENERATOR       ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════╝${NC}\n"

mkdir -p "$CERTS_DIR"
cd "$CERTS_DIR"

echo -e "${BLUE}Step 1: Generating Certificate Authority (CA)...${NC}"
openssl genrsa -out ca.key 2048
openssl req -x509 -new -nodes -key ca.key -sha256 -days 3650 -out ca.crt -subj "/CN=Kuberbolt CA/O=Kuberbolt Platform"
echo -e "${GREEN}✓ CA created${NC}\n"

function generate_cert() {
    NAME=$1
    DNS=$2
    
    echo -e "${BLUE}Generating certificate for $NAME ($DNS)...${NC}"
    
    # Generate private key
    openssl genrsa -out "${NAME}.key" 2048
    
    # Generate CSR
    openssl req -new -key "${NAME}.key" -out "${NAME}.csr" -subj "/CN=${DNS}/O=Kuberbolt Agent"
    
    # Generate extfile for SAN (Subject Alternative Name)
    cat > "${NAME}.ext" << EOF
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:FALSE
keyUsage = digitalSignature, nonRepudiation, keyEncipherment, dataEncipherment
extendedKeyUsage = serverAuth, clientAuth
subjectAltName = @alt_names
[alt_names]
DNS.1 = ${DNS}
DNS.2 = localhost
IP.1 = 127.0.0.1
EOF
    
    # Sign with CA
    openssl x509 -req -in "${NAME}.csr" -CA ca.crt -CAkey ca.key -CAcreateserial -out "${NAME}.crt" -days 825 -sha256 -extfile "${NAME}.ext"
    
    # Cleanup CSR and EXT
    rm "${NAME}.csr" "${NAME}.ext"
    
    # Calculate SHA256 hash of the cert for pinning (strip colons)
    CERT_HASH=$(openssl x509 -in "${NAME}.crt" -pubkey -noout | openssl pkey -pubin -outform der | openssl dgst -sha256 -binary | openssl base64)
    echo -e "${GREEN}✓ Created ${NAME}.crt (Hash: $CERT_HASH)${NC}"
}

# Generate SDK Client Cert
generate_cert "sdk-client" "kuberbolt-sdk"

# Generate FP Certs
generate_cert "fp-client" "fp-client"
generate_cert "fp-provider-1" "fp-provider-1"
generate_cert "fp-provider-2" "fp-provider-2"

echo -e "\n${GREEN}✓ All certificates generated in $CERTS_DIR${NC}"
