# Infrastructure

## Docker Setup

The system runs as a set of containerized workers:

- **arxiv-fetcher**: Runs the scheduler to fetch papers
- **triage-worker**: Paper triage agent
- **pdf-parser**: PDF extraction worker
- **concept-generator**: Concept extraction agent
- **experiment-exploder**: Experiment plan generation
- **notifier**: Slack notification worker

## Database

PostgreSQL with pgvector extension for storing paper metadata.

See database/init-db.sql for initialization.

## Message Queue

RabbitMQ for worker communication.
