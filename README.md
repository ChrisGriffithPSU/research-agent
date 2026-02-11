# Autonomous Quant Research Factory

Autonomous research system for medium-frequency trading (MFT) research with 5-30 second holding times.

## Architecture

The system uses a Pub/Sub worker architecture with deterministic message routing:

```
ArXiv Fetcher (cron) → Paper Triage (LLM) → PDF Parser → Concept Generator (LLM) → [Experiment Exploder]
```

**Workers:**
- **ArXiv Fetcher**: Fetches papers from hardcoded categories (no LLM search)
- **Paper Triage Agent**: Uses LLM to decide REQUEST_FULL_TEXT or REJECT_PAPER
- **PDF Parser**: Extracts text, tables, equations from PDFs (non-LLM)
- **Concept Generator Agent**: Extracts deep concept objects from full text
- **Notifier**: Sends Slack notifications (future)

**Key Features:**
- OpenAI-compatible LLM client with per-agent model overrides
- Local filesystem artifact storage (swappable for S3)
- Cron-based scheduling
- Duplicate detection via database
- Structured JSON contracts between workers

## Configuration

Environment variables:

```bash
# LLM global defaults (OpenAI-compatible endpoint)
CUSTOM_LLM_BASE_URL=https://your-endpoint.com/v1
CUSTOM_LLM_API_KEY=your-api-key
CUSTOM_LLM_MODEL=default-model

# Optional per-agent model overrides
CUSTOM_LLM_TRIAGE_MODEL=triage-model
CUSTOM_LLM_CONCEPT_GEN_MODEL=concept-model
CUSTOM_LLM_EXPERIMENT_EXPLODER_MODEL=experiment-model

# ArXiv Fetcher
ARXIV_FETCH_INTERVAL_MINUTES=30
ARXIV_MAX_RESULTS_PER_CATEGORY=50

# RabbitMQ
RABBITMQ_HOST=localhost
RABBITMQ_PORT=5672
RABBITMQ_USER=guest
RABBITMQ_PASSWORD=guest
RABBITMQ_VIRTUAL_HOST=/

# Storage
ARTIFACTS_BASE_DIR=./artifacts

# Database
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=postgres
DB_NAME=researcher_agent
```

## Usage

### Run the scheduler (fetches papers periodically)
```bash
python -m src.main scheduler --interval 30
```

### Run a specific worker
```bash
# Paper Triage Agent
python -m src.main worker triage

# PDF Parser
python -m src.main worker pdf_parser

# Concept Generator
python -m src.main worker concept_gen

# Kimi Experiment Worker (queue mode)
python -m src.main worker kimi
```

### Run fetcher once (for testing)
```bash
python -m src.main fetch-once
```

### Health check
```bash
python -m src.main health-check
```

## Project Structure

```
src/
├── main.py                 # CLI entry point
├── scheduler.py            # Cron-based scheduler
├── shared/
│   ├── llm/
│   │   └── openai_client.py     # Simplified OpenAI client
│   ├── messaging/               # RabbitMQ infrastructure
│   ├── storage/
│   │   └── artifact_store.py    # Local/S3 storage abstraction
│   ├── interfaces/              # Protocol definitions
│   └── repositories/            # Database repositories
├── workers/
│   ├── arxiv_fetcher/           # ArXiv fetcher worker
│   ├── paper_triage/            # Paper Triage Agent
│   ├── pdf_parser/              # PDF Parser worker
│   ├── concept_generator/       # Concept Generator Agent
│   └── shared/                  # Worker utilities
└── services/fetchers/arxiv/     # Reused ArXiv infrastructure
```

## Message Flow

1. **ArXiv Fetcher** → `paper.triage.request`
2. **Paper Triage** → `paper.triage.decision` + `paper.fulltext.request`
3. **PDF Parser** → `paper.parsed` + `paper.concepts.request`
4. **Concept Generator** → `concepts.generated`

## Development

### Install dependencies
```bash
# ArXiv/PDF environment (docling + pillow<12)
UV_PROJECT_ENVIRONMENT=.venv-arxiv uv sync --extra arxiv

# Main environment (everything else, incl. Kimi)
UV_PROJECT_ENVIRONMENT=.venv-main uv sync --extra main
```

### Run linting
```bash
ruff check src/
```

### Run type checking
```bash
mypy src/
```

### Run tests
```bash
pytest
```

## Research Focus

This system targets **medium-frequency trading research** (5-30s holding times):

- Filters for event-driven, stochastic, partially-observed dynamical systems
- Extracts domain-agnostic concept objects (not features/strategies)
- Produces testable experiment specs (future: coding agent)
- Includes robustness checks: latency, slippage, regime splits
