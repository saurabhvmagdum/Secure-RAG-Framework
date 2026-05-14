# ISRO RAG Framework - Full Setup Guide

This document outlines the full setup procedure to run the ISRO Secure On-Premise RAG Framework locally.

## Prerequisites

- **Docker Desktop** (or Docker Engine + Docker Compose)
- **Node.js 18+** (For local frontend development)
- **Python 3.11+** (For local backend development)

## Option 1: Docker Compose Complete Setup (Recommended)

The most reliable way to run the entire stack is via Docker Compose. This spins up the Nginx Gateway, NextJS Client, FastAPI Backend, Qdrant cluster, OpenSearch indices, Neo4j, and the LLM stub in a sealed bridging network (`isro_internal`).

**1. Prepare Offline Models Directory**
The application uses a simulated inference container (the LLM Stub) which expects a mounted directory. Ensure the directory exists on your host:
```bash
mkdir -p /opt/isro/models
```
*(Note for Windows users: You may need to edit `docker-compose.yml` and adjust the mount volume from `/opt/isro/models` to an absolute Windows path like `C:/opt/isro/models`)*

**2. Start the Cluster**
Within the root of the project, execute:
```bash
docker-compose up -d --build
```
This command builds the required internal images and stands up the infrastructure.

**3. Verify Service Status**
Wait a minute or two for the dependent services (Databases -> Backend -> Gateway) to initialize.
```bash
docker-compose ps
```

**4. Access the Application**
Once fully healthy, the Nginx Gateway uniquely exposes the entire stack securely via port 80:
- **Frontend UI:** Navigate to `http://localhost/` in your browser.
- **Backend APIs:** Protected securely behind `http://localhost/api/`

---

## Option 2: Local Development Setup (Manual Mode)

If you are writing code and prefer hot-reloading without rebuilding containers per change, you can boot just the core infrastructure in Docker and run your backend/frontend processes natively.

**1. Start the Database Infrastructure Only**
Run only the underlying data stores. 
```bash
docker-compose up -d opensearch qdrant neo4j llm_stub
```

**2. Setup and Run the Backend (FastAPI)**
The backend uses Python 3.11+ and relies on `uvicorn` and `fastapi`.
```bash
cd backend
python -m venv venv

# Activate venv (Windows: .\venv\Scripts\activate | Mac/Linux: source venv/bin/activate)
.\venv\Scripts\activate

pip install -e .[dev]
```
Before starting the backend, define environment variables exposing the DBs locally:
```bash
# Windows PowerShell Example
$env:OPENSEARCH_URL="http://localhost:9200"
$env:QDRANT_URL="http://localhost:6333"
$env:NEO4J_URI="bolt://localhost:7687"
$env:LLM_SERVICE_URL="http://localhost:8080"
```
Run the FastAPI application:
```bash
uvicorn app.main:app --reload --port 8000
```

**3. Setup and Run the Frontend (Next.js)**
The frontend requires Node modules populated.
```bash
cd frontend
npm install

# Point the UI to your locally running backend API
$env:INTERNAL_API_URL="http://localhost:8000/api/v1"

npm run dev
```
Navigate to `http://localhost:3000` to interact with your frontend development server.

## Troubleshooting References

- See `deployment_onprem.md` for specific rules regarding strictly air-gapped (offline deployment) production installation requirements.
- Explore files like `ingestion_flow.md` and `retrieval_flow.md` for subsystem specifics.
