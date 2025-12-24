# Docker Compose Setup - Researcher Agent

## Architecture Overview

This project uses **Approach 5: Hybrid (Layered + Profiles)** for Docker Compose:

- **Layered**: Base config + environment-specific overlays (dev/prod)
- **Profiles**: Selective service activation via profiles

## Quick Start

```bash
# 1. Ensure .env is configured
make check-env

# 2. Start infrastructure only
make infra

# 3. Start everything in dev mode
make dev

# 4. View logs
make logs
```

## File Structure

```
infra/docker/
├── docker-compose.yml          # Base configuration with all services
├── docker-compose.dev.yml      # Development overrides (hot reload, exposed ports)
├── docker-compose.prod.yml     # Production overrides (resource limits, logging)
├── Dockerfile.api              # FastAPI services
├── Dockerfile.worker           # Message queue workers
├── Dockerfile.dashboard        # Streamlit dashboard
├── Dockerfile.airflow          # Apache Airflow
└── README.md                   # This file
```

## Profiles

Services are organized into profiles for selective activation:

| Profile | Services | Use Case |
|---------|----------|----------|
| **(none)** | postgres, rabbitmq | Infrastructure only |
| `fetchers` | api-gateway, arxiv-fetcher, kaggle-fetcher, huggingface-fetcher, web-search-fetcher | Content discovery |
| `intelligence` | llm-router, deduplication, extraction, synthesis | LLM processing pipeline |
| `delivery` | digest-generation, search, dashboard | User-facing services |
| `learning` | feedback, learning | ML/personalization |
| `orchestration` | airflow | Workflow scheduling |
| `all` | Everything | Full system |
| `dev` | dashboard (also included in delivery) | Development tools |

## Usage Examples

### Development

```bash
# Infrastructure only (postgres + rabbitmq)
docker-compose -f docker-compose.yml up

# OR use Make
make infra

# Start fetchers for development
docker-compose -f docker-compose.yml -f docker-compose.dev.yml --profile fetchers up

# OR use Make
make fetchers

# Start everything with hot reload
docker-compose -f docker-compose.yml -f docker-compose.dev.yml --profile all up

# OR use Make
make dev
```

### Production

```bash
# Build images
docker-compose -f docker-compose.yml build

# Start all services in production mode (detached)
docker-compose -f docker-compose.yml -f docker-compose.prod.yml --profile all up -d

# OR use Make
make prod

# View logs
docker-compose -f docker-compose.yml logs -f

# OR use Make
make logs
```

### Combining Profiles

```bash
# Start infrastructure + fetchers + intelligence
docker-compose -f docker-compose.yml --profile fetchers --profile intelligence up

# Start delivery + learning
docker-compose -f docker-compose.yml --profile delivery --profile learning up
```

## Service Ports (Dev Mode)

| Service | Port | URL |
|---------|------|-----|
| PostgreSQL | 5432 | `localhost:5432` |
| RabbitMQ | 5672, 15672 | Management UI: `http://localhost:15672` |
| API Gateway | 8001 | `http://localhost:8001` |
| LLM Router | 8002 | `http://localhost:8002` |
| Digest Generation | 8003 | `http://localhost:8003` |
| Search API | 8004 | `http://localhost:8004` |
| Feedback API | 8005 | `http://localhost:8005` |
| Dashboard | 8501 | `http://localhost:8501` |
| Airflow | 8080 | `http://localhost:8080` |

## Environment Variables

Docker Compose automatically reads from the root `.env` file.

**Docker-specific overrides:**
- `DB_HOST=postgres` (instead of localhost)
- `RABBITMQ_HOST=rabbitmq` (instead of localhost)

These are set inline in docker-compose.yml.

## Development Features (docker-compose.dev.yml)

- **Hot Reload**: Code changes reflected immediately (via volume mounts)
- **Exposed Ports**: All services accessible from host
- **Debug Logging**: `LOG_LEVEL=DEBUG`
- **No Resource Limits**: Faster iteration

## Production Features (docker-compose.prod.yml)

- **Resource Limits**: CPU/memory constraints per service
- **Structured Logging**: JSON logs with rotation
- **Health Checks**: Automated health monitoring
- **Restart Policies**: Auto-restart on failure
- **Security**: Minimal exposed ports

## Common Commands

```bash
# Build all images
make build

# Build without cache (force rebuild)
make build-no-cache

# View running services
make ps

# Tail logs
make logs

# Stop all services
make clean

# Stop and remove volumes (deletes data!)
make clean-volumes

# Restart services
make restart

# Open PostgreSQL shell
make db-shell

# Run database migrations
make migrate

# Run tests
make test

# Lint code
make lint
```

## Troubleshooting

### Services won't start

```bash
# Check logs
docker-compose -f docker-compose.yml logs <service-name>

# Check if .env is configured
make check-env

# Rebuild images
make build-no-cache
```

### Port conflicts

If you get "port already in use" errors:

```bash
# Check what's using the port
lsof -i :5432  # Example for PostgreSQL

# Kill the process or change port in docker-compose.yml
```

### Database connection issues

```bash
# Ensure postgres is healthy
docker ps  # Check STATUS column

# Check postgres logs
docker logs researcher-postgres

# Connect manually
docker exec -it researcher-postgres psql -U postgres
```

### RabbitMQ connection issues

```bash
# Check RabbitMQ health
docker logs researcher-rabbitmq

# Access management UI
open http://localhost:15672
# Default credentials: guest/guest
```

## Resource Requirements

### Minimum (Infrastructure Only)

- CPU: 2 cores
- RAM: 4GB
- Disk: 10GB

### Recommended (All Services)

- CPU: 4 cores
- RAM: 8GB
- Disk: 20GB

### Production (All Services with Headroom)

- CPU: 8 cores
- RAM: 16GB
- Disk: 50GB

## Next Steps

1. Configure your `.env` file with API keys
2. Start infrastructure: `make infra`
3. Test database connection: `make db-shell`
4. Start specific profile: `make fetchers`
5. View logs: `make logs`
6. Access services via exposed ports

## References

- [Docker Compose Profiles](https://docs.docker.com/compose/profiles/)
- [Docker Compose File Reference](https://docs.docker.com/compose/compose-file/)
- [Docker Best Practices](https://docs.docker.com/develop/dev-best-practices/)
