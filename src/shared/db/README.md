# Database Layer - Researcher Agent

Complete database setup with connection pooling, session management, and repository pattern.

## Architecture

### Components

1. **Models** (`src/shared/models/`)
   - `user.py` - User profiles and preferences
   - `source.py` - Fetched content with vector embeddings
   - `digest.py` - Daily digests and digest items
   - `feedback.py` - User feedback for learning
   - `system.py` - System state, fetcher tracking, model metadata

2. **Database Configuration** (`src/shared/db/config.py`)
   - `DatabaseConfig` - Pydantic settings from environment variables
   - `create_async_engine()` - Factory for configured async engine
   - Connection pooling: 5 connections, 10 overflow, 3600s recycle
   - Pool pre-ping for connection health

3. **Session Management** (`src/shared/db/session.py`)
   - `get_async_session()` - Dependency injection for FastAPI
   - `DatabaseSession` - Context manager for manual usage
   - Async transaction handling with automatic commit/rollback

4. **Repository Layer** (`src/shared/repositories/`)
   - `base.py` - Generic CRUD + vector search mixin
   - `user_repository.py` - User profile operations
   - `source_repository.py` - Source operations + vector similarity
   - `digest_repository.py` - Digest and digest item operations
   - `feedback_repository.py` - Feedback aggregation
   - `system_repository.py` - System state, fetcher tracking, model metadata

5. **Migrations** (`src/shared/db/migrations/`)
   - `20241222_initial_schema.py` - Core tables (user, source, digest, feedback)
   - `20241223_add_system_tables.py` - System tables (state, fetcher, queries, model, weights)

6. **Seeding** (`src/shared/db/seed.py`)
   - Default user profile
   - System state configuration
   - Fetcher states initialization
   - Idempotent (can run multiple times safely)

## Usage

### Configuration

Set environment variables (or use defaults):

```bash
DB_HOST=localhost              # Database host (postgres in Docker, localhost locally)
DB_PORT=5432                  # Database port
DB_USER=postgres                # Database user
DB_PASSWORD=postgres            # Database password
DB_NAME=researcher_agent        # Database name
```

Optional configuration (YAML can be added later):

```bash
DATABASE_POOL_SIZE=5            # Connection pool size
DATABASE_MAX_OVERFLOW=10         # Max overflow connections
DATABASE_POOL_RECYCLE=3600     # Recycle connections (seconds)
DATABASE_POOL_TIMEOUT=30        # Connection timeout (seconds)
DATABASE_ECHO=false              # Log SQL statements (DEBUG mode)
```

### Using Repositories

#### FastAPI (Dependency Injection)

```python
from fastapi import Depends, APIRouter
from src.shared.db.session import get_async_session
from src.shared.repositories import UserRepository

router = APIRouter()

@router.get("/users/{user_id}")
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_async_session),
):
    user_repo = UserRepository(db)
    user = await user_repo.get(user_id)
    return user
```

#### Manual (Context Manager)

```python
from src.shared.db.session import DatabaseSession
from src.shared.repositories import SourceRepository

async def fetch_and_store():
    async with DatabaseSession() as session:
        source_repo = SourceRepository(session)
        source = await source_repo.create(
            source_type=SourceType.ARXIV,
            url="https://arxiv.org/abs/1234.5678",
            title="Test Paper",
            content="Paper content...",
            metadata={},
        )
        # Session commits and closes automatically
```

### Vector Search

```python
from src.shared.repositories import SourceRepository

async def find_duplicates():
    async with DatabaseSession() as session:
        source_repo = SourceRepository(session)

        # Check for semantic duplicates
        query_embedding = [0.1, 0.2, ...]  # 1536 dims
        similar = await source_repo.find_similar(
            embedding=query_embedding,
            threshold=0.85,  # Cosine similarity
            limit=10,
        )
        return similar

# Hybrid duplicate detection (URL + semantic)
async def check_duplicate(url: str, embedding: list):
    async with DatabaseSession() as session:
        source_repo = SourceRepository(session)
        is_dup, dup_type = await source_repo.is_duplicate_hybrid(
            url=url,
            embedding=embedding,
            threshold=0.85,
        )
        if is_dup:
            print(f"Duplicate detected: {dup_type}")
        return is_dup
```

## Running Migrations

### Apply New Migration

```bash
# Add system tables to database
uv run alembic -c src/shared/db/migrations/alembic.ini upgrade head
```

### Create New Migration

```bash
# Auto-generate from model changes
uv run alembic -c src/shared/db/migrations/alembic.ini revision --autogenerate -m "description"

# Create empty migration
uv run alembic -c src/shared/db/migrations/alembic.ini revision -m "description"
```

### Check Migration Status

```bash
# Current version
uv run alembic -c src/shared/db/migrations/alembic.ini current

# History
uv run alembic -c src/shared/db/migrations/alembic.ini history

# Rollback one migration
uv run alembic -c src/shared/db/migrations/alembic.ini downgrade -1
```

## Seeding Database

### Run Seeding

```bash
# Seed initial data
uv run python -m src.shared.db.seed
```

This creates:
- Default user profile (ID: 1, email: user@example.com)
- System state configuration (feature flags, digest settings)
- Fetcher states (arxiv, kaggle, huggingface, web_search)

## Testing

### Run Tests

```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/unit/shared/repositories/test_base_repository.py

# Run with coverage
uv run pytest --cov=src/shared --cov-report=html

# Run specific test
uv run pytest -k "test_base_repository_create"
```

### Test Fixtures

Tests use in-memory SQLite for speed. Fixtures provide:

- `test_engine` - Async engine with all tables created
- `test_session` - Async session (commits/rolls back automatically)
- `test_config` - Test database configuration

### Test Factories

```python
from tests.factories import create_source, create_embedding

# Create test data
source = await repo.create(**create_source(id=1))

# Create embedding for vector tests
embedding = create_embedding(dims=1536)
```

## Troubleshooting

### Connection Issues

```bash
# Check if PostgreSQL is running
docker ps | grep postgres

# Check logs
docker logs researcher-postgres

# Test connection from host
psql -h localhost -p 5432 -U postgres -d researcher_agent

# Test connection from container
docker exec -it researcher-postgres psql -U postgres
```

### Migration Issues

```bash
# Check current migration
uv run alembic -c src/shared/db/migrations/alembic.ini current

# Stamp database at specific revision (if out of sync)
uv run alembic -c src/shared/db/migrations/alembic.ini stamp head

# Reset to baseline (nuclear option)
uv run alembic -c src/shared/db/migrations/alembic.ini downgrade base
uv run alembic -c src/shared/db/migrations/alembic.ini upgrade head
```

### Vector Index Issues

```bash
# Check if pgvector extension is installed
docker exec -it researcher-postgres psql -U postgres -c "\dx"

# Rebuild vector index if corrupted
docker exec -it researcher-postgres psql -U postgres -c "REINDEX INDEX ix_sources_embedding_hnsw;"

# Verify index exists
docker exec -it researcher-postgres psql -U postgres -c "\di sources"
```

## Database Schema

### Core Tables (Migration 001)

1. **user_profiles** - User preferences and settings
2. **sources** - Raw content with vector embeddings (HNSW index)
3. **digests** - Daily digests with delivery status
4. **digest_items** - Individual digest items with rankings
5. **feedback** - User ratings and interaction data

### System Tables (Migration 002)

6. **system_state** - Key-value store for configuration
7. **fetcher_state** - Fetcher health and error tracking
8. **search_queries** - LLM query history for deduplication
9. **model_metadata** - Learning model versioning
10. **preference_weights** - Learned preference scores

## Performance

### Connection Pooling

- **Pool size**: 5 connections per service
- **Max overflow**: 10 additional connections
- **Recycle**: Every 3600 seconds (1 hour)
- **Timeout**: 30 seconds to acquire connection

This configuration supports:
- 5 concurrent database operations per service (normal load)
- 15 concurrent operations during spikes (overflow)
- Automatic connection recycling prevents stale connections

### Vector Search

- **Index**: HNSW (Hierarchical Navigable Small World)
- **Dimensions**: 1536 (OpenAI text-embedding-3-small)
- **Distance metric**: Cosine distance (`<=>`)
- **Similarity threshold**: 0.85 (configurable)
- **Performance**: O(log n) for approximate search

### Query Optimization

- **Indexes**: All foreign keys, status fields, dates
- **Eager loading**: `selectinload()` for relationships
- **Pagination**: Cursor-based for large datasets
- **Batch operations**: `bulk_insert_mappings()` for inserts

## Health Checks

The database layer includes health check endpoints for monitoring:

### Endpoints

- **`GET /health`** - Detailed health check including:
  - Overall status (healthy/unhealthy)
  - Database connection status
  - Query execution status
  - Connection pool information
  - Timestamp

- **`GET /health/quick`** - Quick liveness check:
  - Returns 200 OK if connection works
  - Returns 503 Service Unavailable if connection fails
  - Used by load balancers and Kubernetes probes

- **`GET /health/liveness`** - Kubernetes liveness probe:
  - Simple OK response (no DB check)
  - Indicates application is running

- **`GET /health/readiness`** - Kubernetes readiness probe:
  - Checks if database connection works
  - Returns ready/not_ready status
  - Indicates if application can accept traffic

### Using Health Checks

**Programmatically:**
```python
from src.shared.db.health import check_health, quick_check

# Detailed health check
health = await check_health()
print(health)
# Returns: {"status": "healthy", "checks": {...}}

# Quick check
is_healthy = await quick_check()
print(is_healthy)
# Returns: True/False
```

**Via HTTP:**
```bash
# Full health check
curl http://localhost:8000/health

# Quick liveness
curl http://localhost:8000/health/quick

# Kubernetes readiness probe
curl http://localhost:8000/health/readiness
```

### Integration

Add health router to your FastAPI app:

```python
from src.shared.api.health_router import router as health_router

app = FastAPI()
app.include_router(health_router)
```

Now your services have:
- Automatic health monitoring
- Kubernetes probe support
- Load balancer integration
- Simple debugging endpoint

### Health Check Results

**Healthy Response (200):**
```json
{
  "status": "healthy",
  "timestamp": "2024-12-23T12:00:00Z",
  "checks": {
    "connection": "ok",
    "query": "ok",
    "pool": {
      "size": 5,
      "overflow": 0,
      "checkedin": 3
    }
  }
}
```

**Unhealthy Response (503):**
```json
{
  "status": "unhealthy",
  "error": "connection timeout",
  "timestamp": "2024-12-23T12:00:00Z",
  "checks": {
    "connection": "failed",
    "connection_error": "could not connect to server"
  }
}
```

## Next Steps

1. **Create database**: Run migrations with `uv run alembic upgrade head`
2. **Seed data**: Run `uv run python -m src.shared.db.seed`
3. **Test connectivity**: Verify services can connect
4. **Implement services**: Use repositories in fetchers, extraction, synthesis, etc.
5. **Add monitoring**: Set up logging and metrics collection

## Dependencies

- `sqlalchemy>=2.0.25` - ORM and async support
- `alembic>=1.13.0` - Database migrations
- `psycopg2-binary>=2.9.9` - PostgreSQL driver
- `pgvector>=0.2.4` - Vector similarity search
- `pydantic-settings>=2.1.0` - Configuration management
- `asyncpg` - Async PostgreSQL driver (installed with psycopg2-binary)

