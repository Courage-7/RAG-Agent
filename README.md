# RAG Agent

An adaptive, evaluation-driven RAG platform capable of selecting the cheapest and simplest retrieval strategy that produces sufficient evidence, escalating to more sophisticated retrieval or agentic research only when justified.

## Foundation status

The repository is being rebuilt as a Python 3.12 `uv` workspace. The current foundation includes:

- a FastAPI service with liveness/readiness endpoints;
- a provider-neutral model port backed by Groq `ChatGroq` profiles;
- typed, versioned job envelopes and state transitions;
- a Redis/Dramatiq queue adapter and worker skeleton;
- a Supabase migration for authoritative job and transactional-outbox state with RLS/grant tests;
- locked dependencies, unit/contract tests, Docker Compose, and GitHub Actions.

The obsolete Streamlit/FAISS prototype has been removed; the repository now contains only the new architecture and implementation.

## Start locally

Prerequisites are Python 3.12, `uv`, Docker, and Supabase CLI 2.115.0 or compatible.

```bash
cp .env.example .env
uv sync --locked --all-packages --dev
supabase start
supabase db reset --local
docker compose up -d redis-broker
uv run --frozen --package rag-api uvicorn rag_api.main:app --reload
```

Run the worker in a second terminal:

```bash
uv run --frozen --package rag-worker dramatiq rag_worker.app
```

See the [foundation notebook](notebooks/rag_demo.ipynb) for an executable walkthrough,
[local development](docs/runbooks/local-development.md) for setup and verification,
[credentials and services](docs/configuration/credentials-and-services.md) for every value you will
need to provide, the [canonical architecture](docs/architecture/rag-agent-plan.md) for the
complete roadmap, and the [ADR index](docs/adr/README.md) for binding decisions.
