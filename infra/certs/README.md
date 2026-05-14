# mTLS Certificate Generation

This directory holds TLS certificates for internal service communication. **Never commit actual certificates or keys to version control.**

## Certificate Requirements

All in-cluster communication uses mutual TLS (mTLS) with the following specifications:

| Parameter | Value |
|-----------|-------|
| Protocol | TLS 1.3 |
| Key Algorithm | RSA 4096 or ECDSA P-256 |
| Signature | SHA-256 |
| Certificate Validity | 365 days (rotate annually) |
| Client Auth | Required (mutual TLS) |

## Internal CA Setup

```bash
# 1. Generate internal CA key and certificate
openssl req -x509 -newkey rsa:4096 \
    -keyout ca.key -out ca.crt \
    -days 3650 -nodes \
    -subj "/O=ISRO/OU=RAG Framework/CN=ISRO Internal CA"

# 2. Generate server key and CSR
openssl req -newkey rsa:4096 \
    -keyout server.key -out server.csr -nodes \
    -subj "/O=ISRO/OU=RAG Framework/CN=isro-rag-backend"

# 3. Sign server certificate with CA
openssl x509 -req -in server.csr \
    -CA ca.crt -CAkey ca.key -CAcreateserial \
    -out server.crt -days 365 \
    -extfile <(printf "subjectAltName=DNS:isro-rag-backend,DNS:localhost,IP:127.0.0.1")

# 4. Generate client certificate for frontend → backend mTLS
openssl req -newkey rsa:4096 \
    -keyout client.key -out client.csr -nodes \
    -subj "/O=ISRO/OU=RAG Framework/CN=isro-rag-frontend"

openssl x509 -req -in client.csr \
    -CA ca.crt -CAkey ca.key -CAcreateserial \
    -out client.crt -days 365
```

## Per-Service Certificates

Generate additional certificates for:
- `opensearch` — OpenSearch node-to-node and REST API
- `qdrant` — Qdrant gRPC and HTTP API
- `neo4j` — Neo4j Bolt protocol
- `backend` — FastAPI server
- `frontend` — Next.js (terminated at ingress)

## Key Rotation Policy

1. Certificates must be rotated at least annually
2. CA key must be stored in on-prem HSM or encrypted vault
3. Old certificates must be revoked via CRL
4. Rotation events logged as audit events (KEY_ROTATION action)

## File Layout (Expected)

```
certs/
├── ca.crt                  # Internal CA certificate
├── ca.key                  # Internal CA key (PROTECT)
├── server.crt              # Backend server certificate
├── server.key              # Backend server key (PROTECT)
├── client.crt              # Frontend client certificate
├── client.key              # Frontend client key (PROTECT)
├── opensearch-ca.pem       # OpenSearch CA
├── qdrant-ca.pem           # Qdrant CA
└── neo4j-ca.pem            # Neo4j CA
```

> ⚠️ **NEVER** commit `.key` or `.pem` files to version control.
> All keys must be stored in an on-prem secrets management system.
