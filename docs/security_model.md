# Security Model

The ISRO Secure On-Premise RAG Framework strictly adheres to `.antigravityrules`.

## Component Boundaries
1. **Frontend (Next.js)**
   - Fully isolated display layer.
   - Makes explicit POST calls strictly to the gateway `/api/v1/query`.
   - Never trusts token logic manually; delegates authorization purely to the backend endpoints.
2. **Gateway (Nginx)**
   - Drops any external network scanning explicitly seeking out ports `7687` (Neo4j), `6333` (Qdrant), or `9200` (OpenSearch).
3. **Backend Service**
   - Applies strict RBAC bounds natively into the database Driver clients before extraction.
   - Runs `FallbackFormatter` converting unauthorized or uncertain hallucinations implicitly into nil blocks.

## Token Exudation
JWT tokens execute cross-component tracking mapping the `Principal` safely across the loop without interacting locally with `localStorage` configurations on the browser shell. Future LDAP upgrades securely bridge this payload behind reverse proxies directly.
