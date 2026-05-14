# Offline Deployment Model

## Prerequisites
- Flat network environment (Isolating the internal components)
- No outbound WAN access. 
- A mountable host directory holding the unzipped `isro_models.tar.gz`.

## Volumes
- `/opt/isro/models` (Host) -> `/models` (Container - `llm_stub`)
- This directory must contain the GGUF instances for standard offline invocation.

## Startup
```bash
# Extract offline components
mkdir -p /opt/isro/models
# Load pre-pulled offline Docker images (supplied securely via USB)
docker load -i isro-qdrant.tar
docker load -i isro-neo4j.tar
docker load -i isro-os.tar

# Execute Topology
docker-compose up -d
```

## Internal Networking Topology
The `docker-compose.yml` configures an `isro_internal` bridge network.
Only the **Nginx Gateway** holds a bound port mapping (e.g. `80:80`).
Users attempting to access `http://qdrant:6333` directly will fail, preventing raw access bypasses.

## Image Management
Since the cluster cannot leverage `npm install` or `pip install`, all custom images (`frontend`, `backend`) must be built locally on the secure staging host or transferred entirely as pre-baked `.tar` images matching the declarative infrastructure.
