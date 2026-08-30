# Local development runbook

## Prerequisites

- Python 3.12
- `uv` compatible with the range in `pyproject.toml`
- Docker with Compose
- Supabase CLI 2.115.0 or compatible
- a Groq API key for opt-in live inference only

On Windows/WSL, enable Docker Desktop integration for the WSL distribution before starting Supabase or Redis.

## Bootstrap

```bash
cp .env.example .env
uv sync --locked --all-packages --dev
supabase start
supabase db reset --local
supabase test db
docker compose up -d redis-broker
```

Put `GROQ_API_KEY` in the untracked `.env`. Never put a service-role key, Groq key, SMTP credential, connector token, or production database URL in tracked files.

## Run processes

API:

```bash
uv run --frozen --package rag-api uvicorn rag_api.main:app --reload
```

Worker, in another terminal:

```bash
uv run --frozen --package rag-worker dramatiq rag_worker.app
```

Check the service:

```bash
curl --fail http://127.0.0.1:8000/health/live
curl --fail http://127.0.0.1:8000/health/ready
```

Liveness does not contact dependencies. Readiness currently verifies required configuration; active Redis, Postgres, and Groq capability probes are a later foundation slice.

## Quality gates

```bash
uv lock --check
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen mypy apps packages tests
uv run --frozen pytest tests -q
uv run --frozen jupyter execute --inplace --timeout=60 notebooks/rag_demo.ipynb
supabase db lint --local --level error --fail-on error
supabase test db
```

Unit tests and the foundation notebook do not make live Groq calls. The notebook uses a fake
LangChain chat runtime and in-process FastAPI transport. Live provider smoke tests will be opt-in
and must use a restricted development project.

## Stop local services

```bash
docker compose down
supabase stop --no-backup
```

Omit `--no-backup` when local database state should be retained. Do not use volume-removal flags unless losing all local broker data is intentional.

## Known foundation limits

- Docker is required to validate the Redis and local Supabase paths.
- The worker actor currently validates a demo envelope; authoritative claim/lease/outbox transitions are the next vertical slice.
- Authentication, documents, embeddings, hybrid retrieval, LangGraph, and Composio connectors begin in later milestones after the durable job slice passes recovery tests.
