# Database Setup - PostgreSQL + pgvector

## Overview

This directory contains database initialization scripts for Researcher Agent.

**Approach**: Hybrid (Init Scripts + Alembic)
- **Init scripts** (this directory): Infrastructure setup (extensions, users)
- **Alembic migrations** (`src/shared/db/migrations/`): Application schema (tables, indexes)

## Files

- `init-db.sql` - Runs automatically on first PostgreSQL container startup
  - Enables pgvector extension
  - Sets up database-level configurations

## Quick Start

### 1. Start PostgreSQL

```bash
# Start infrastructure (postgres + rabbitmq)
make infra
```

The init script runs automatically and enables the pgvector extension.

### 2. Run Migrations

```bash
# Run Alembic migrations to create tables
make migrate
```

This creates all application tables:
- `user_profiles` - User preferences and settings
- `sources` - Raw content from fetchers with vector embeddings
- `digests` - Daily curated digests
- `digest_items` - Individual items in digests
- `feedback` - User feedback for learning system

### 3. Verify Setup

```bash
# Open PostgreSQL shell
make db-shell

# Inside psql:
# List extensions
\dx

# List tables
\dt

# Check vector extension
SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';

# Exit
\q
```

## Schema Management

### Create New Migration

```bash
# Auto-generate migration from model changes
uv run alembic -c src/shared/db/migrations/alembic.ini revision --autogenerate -m "description"

# Or create empty migration
uv run alembic -c src/shared/db/migrations/alembic.ini revision -m "description"
```

### Apply Migrations

```bash
# Upgrade to latest
make migrate

# Or manually:
uv run alembic -c src/shared/db/migrations/alembic.ini upgrade head

# Upgrade to specific revision
uv run alembic -c src/shared/db/migrations/alembic.ini upgrade <revision>

# Downgrade one revision
uv run alembic -c src/shared/db/migrations/alembic.ini downgrade -1
```

### Migration History

```bash
# Show current revision
uv run alembic -c src/shared/db/migrations/alembic.ini current

# Show migration history
uv run alembic -c src/shared/db/migrations/alembic.ini history
```

## Vector Similarity Search

The `sources` table includes a `embedding` column (1536 dimensions) with HNSW index for fast similarity search.

### Example Queries

```sql
-- Find similar sources by cosine similarity
SELECT id, title, 1 - (embedding <=> '[0.1, 0.2, ...]'::vector) AS similarity
FROM sources
WHERE embedding IS NOT NULL
ORDER BY embedding <=> '[0.1, 0.2, ...]'::vector
LIMIT 10;

-- Find sources within a similarity threshold
SELECT id, title
FROM sources
WHERE embedding IS NOT NULL
  AND 1 - (embedding <=> '[0.1, 0.2, ...]'::vector) > 0.8;
```

### Similarity Operators

- `<=>` - Cosine distance (0 = identical, 2 = opposite)
- `<#>` - Negative inner product
- `<->` - Euclidean distance (L2)

The HNSW index uses `vector_cosine_ops` for fast approximate nearest neighbor search.

## Troubleshooting

### Init script didn't run

```bash
# If postgres container already exists, init scripts won't run
# Solution: Remove volume and recreate

make clean-volumes  # WARNING: Deletes all data!
make infra
make migrate
```

### Migration errors

```bash
# Check Alembic current state
uv run alembic -c src/shared/db/migrations/alembic.ini current

# Stamp database at specific revision (if out of sync)
uv run alembic -c src/shared/db/migrations/alembic.ini stamp <revision>

# Reset to baseline (nuclear option)
uv run alembic -c src/shared/db/migrations/alembic.ini downgrade base
uv run alembic -c src/shared/db/migrations/alembic.ini upgrade head
```

### Connection refused

```bash
# Check if postgres is running
docker ps | grep postgres

# Check logs
docker logs researcher-postgres

# Verify environment variables
grep DB_ .env
```

## Database Credentials

**Development** (from .env):
- Host: `localhost` (or `postgres` inside Docker network)
- Port: `5432`
- Database: `researcher_agent`
- User: `postgres`
- Password: `postgres`

**Production**: Change credentials in production deployment!

## Backup and Restore

```bash
# Backup
docker exec researcher-postgres pg_dump -U postgres researcher_agent > backup.sql

# Restore
cat backup.sql | docker exec -i researcher-postgres psql -U postgres -d researcher_agent
```

## Next Steps

1. Start infrastructure: `make infra`
2. Run migrations: `make migrate`
3. Verify setup: `make db-shell` and check tables
4. Start building services that use the database
