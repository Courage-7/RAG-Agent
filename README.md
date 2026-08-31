# RAG Agent

An adaptive, evaluation-driven RAG platform. By default it uses the cheapest and simplest retrieval strategy that produces sufficient evidence, escalating to more sophisticated retrieval or bounded agentic research only when warranted by evaluation scores.

---

## Status

**Foundation phase.** The repository is a Python 3.12 `uv` workspace. The implemented foundation includes:

- FastAPI service with liveness / readiness health endpoints
- Provider-neutral `ChatModelPort` backed by a `langchain-groq` adapter with three capability profiles
- Typed, versioned `JobEnvelope` with an enforced status state machine
- Dramatiq / Redis worker transport with a `demo_job` actor proving the round-trip boundary
- `DramatiqJobQueue` adapter implementing the queue port with transactional-outbox semantics
- Tool approval and idempotency contracts for future Composio-connected actions
- Supabase migration establishing the authoritative job-state schema with RLS and grant tests
- Full quality gate: `ruff`, `mypy` (strict), `pytest`, notebook execution, DB lint/test, secret scan

Upcoming slices: durable claim / lease / outbox transitions → document ingestion actor → embeddings → hybrid retrieval → LangGraph agent → Composio connectors.

---

## Architecture

```
                    ┌──────────────────────────────┐
                    │         FastAPI API           │  apps/api  •  rag-api
                    │  GET /health/live             │
                    │  GET /health/ready            │
                    └──────────────┬───────────────┘
                                   │  JobEnvelope (Redis / Dramatiq)
                    ┌──────────────▼───────────────┐
                    │       Dramatiq Worker         │  apps/worker  •  rag-worker
                    │  demo_job  (maintenance queue)│
                    │  (document_ingestion planned) │
                    │  (embedding_batch planned)    │
                    └──────────────┬───────────────┘
                                   │
                    ┌──────────────▼───────────────┐
                    │    rag-core (shared library)  │  packages/core
                    │  jobs • retrieval • models    │
                    │  tools • observability        │
                    └──────────┬──────────┬────────┘
                               │          │
                    ┌──────────▼──┐  ┌────▼──────────┐
                    │  Supabase   │  │   Redis 8      │
                    │  Postgres   │  │   (Dramatiq    │
                    │  pgvector   │  │    broker)     │
                    │  Auth       │  └───────────────-┘
                    │  Storage    │
                    │  RLS        │
                    └─────────────┘
```

### Retrieval escalation ladder _(evaluation-gated, ADR-007 — planned)_

| Tier | `RetrievalStrategy` | Trigger |
|------|---------------------|---------|
| 1 | `hybrid` — dense + lexical + RRF fusion | Default |
| 2 | `multi_query` — parallel query variants | Eval score below threshold |
| 3 | `decomposition` — sub-question decomposition | Complex / multi-hop queries |
| 4 | `web_fallback` — bounded LangGraph agent + Tavily / Exa | No sufficient local evidence |

The `RetrievalStrategy` enum and `GroundedAnswer` / `RetrievedChunk` contracts are defined in `rag-core`; the retrieval runners are a future milestone.

---

## Repository layout

```
.
├── apps/
│   ├── api/                  # rag-api — FastAPI service
│   │   └── src/rag_api/
│   │       └── main.py       # create_app(), /health/live, /health/ready
│   └── worker/               # rag-worker — Dramatiq background worker
│       └── src/rag_worker/
│           ├── app.py        # Broker setup + actor imports
│           ├── tasks/
│           │   └── demo.py   # demo_job actor (maintenance queue)
│           └── infrastructure/
│               └── dramatiq_queue.py  # DramatiqJobQueue (queue port impl)
├── packages/
│   └── core/                 # rag-core — shared domain contracts
│       └── src/rag_core/
│           ├── config.py          # AppSettings (pydantic-settings)
│           ├── errors.py          # Typed RagError hierarchy
│           ├── jobs/
│           │   ├── models.py      # JobEnvelope, JobStatus, JobStage, DispatchReceipt
│           │   └── ports.py       # JobQueuePort protocol
│           ├── models/
│           │   ├── contracts.py   # ChatModelPort, ModelRequest/Response
│           │   ├── profiles.py    # ModelProfile, ModelPurpose, default_groq_profiles()
│           │   └── groq.py        # ChatGroq adapter
│           ├── retrieval/
│           │   ├── models.py      # RetrievalQuery, RetrievedChunk, GroundedAnswer
│           │   └── ports.py       # RetrieverPort protocol
│           ├── tools/
│           │   └── models.py      # ToolCallIntent, ApprovalGrant, ToolPolicy
│           └── observability/
│               └── logging.py     # structlog configuration
├── docs/
│   ├── adr/                       # 12 Architecture Decision Records
│   ├── architecture/              # Canonical plan + amendment (decision history)
│   ├── configuration/             # Credentials and services reference
│   └── runbooks/
│       └── local-development.md  # Authoritative local setup guide
├── evals/                         # Evaluation datasets (harness: planned)
├── infrastructure/
│   ├── docker/Dockerfile          # Shared multi-stage image
│   └── redis/redis.conf
├── notebooks/                  # rag_demo.ipynb — executable walkthrough
├── supabase/                   # Migrations and RLS/grant tests
└── tests/
    ├── unit/
    └── contract/
```

---

## Prerequisites

| Tool | Version |
|------|---------|
| Python | 3.12.x |
| [uv](https://docs.astral.sh/uv/) | ≥ 0.10.3, < 0.13 |
| Docker + Docker Compose | any recent |
| [Supabase CLI](https://supabase.com/docs/guides/local-development) | 2.115.0 or compatible |

---

## Quick start (local)

### 1. Copy and fill environment variables

```bash
cp .env.example .env
```

Edit `.env` and supply at minimum:

| Variable | Description |
|----------|-------------|
| `GROQ_API_KEY` | Groq API key |
| `RAG_SUPABASE_PUBLISHABLE_KEY` | Supabase anon key (printed by `supabase start`) |

See [credentials and services](docs/configuration/credentials-and-services.md) for every value.

### 2. Install dependencies

```bash
uv sync --locked --all-packages --dev
```

### 3. Start Supabase

```bash
supabase start
supabase db reset --local
```

### 4. Start Redis

```bash
docker compose up -d redis-broker
```

### 5. Run the API

```bash
uv run --frozen --package rag-api uvicorn rag_api.main:app --reload
```

API available at <http://127.0.0.1:8000>. Health endpoints:

- `GET /health/live` — liveness probe
- `GET /health/ready` — readiness probe (checks Groq, Redis, Postgres config)

### 6. Run the worker (second terminal)

```bash
uv run --frozen --package rag-worker dramatiq rag_worker.app
```

---

## Full Docker Compose stack

Runs the API, worker, and Redis together (Supabase must still be started separately):

```bash
docker compose up
```

| Service | Port |
|---------|------|
| `redis-broker` | 127.0.0.1:6379 |
| `api` | 127.0.0.1:8000 |
| `worker` | — |

---

## Development

### Run tests

```bash
uv run --frozen pytest
```

### Type-check

```bash
uv run --frozen mypy apps packages tests
```

### Lint and format

```bash
uv run --frozen ruff check .
uv run --frozen ruff format .
```

### Interactive notebook

See [notebooks/rag_demo.ipynb](notebooks/rag_demo.ipynb) for an executable walkthrough of the retrieval pipeline.

---

## Key packages

| Package | Description |
|---------|-------------|
| `rag-api` | FastAPI application factory, health endpoints, future RAG HTTP routes |
| `rag-worker` | Dramatiq worker entry point; processes `document_ingestion`, `embedding_batch`, and `maintenance` jobs |
| `rag-core` | All shared domain models, port interfaces, and infrastructure adapters |

### Model profiles (ADR-008)

Three capability profiles are pre-configured in `rag-core`:

| Profile | Model | Use case |
|---------|-------|----------|
| `fast` | `openai/gpt-oss-20b` | Low-latency, high-volume retrieval tasks |
| `quality` | `openai/gpt-oss-120b` | High-quality answer synthesis |
| `agent` | `openai/gpt-oss-120b` | Bounded LangGraph agent execution |

### Job state machine

```
QUEUED → RUNNING → COMPLETED
                 ↘ RETRY_SCHEDULED → RUNNING
                 ↘ FAILED
                 ↘ DEAD_LETTER
                 ↘ CANCELLED
```

Stages within a running job:
`validating → parsing → normalizing → chunking → enriching → embedding → indexing → verifying → completed`

---

## Architecture decisions

12 binding ADRs govern this project. See the [ADR index](docs/adr/README.md) for the full list.

| ADR | Decision | Status |
|-----|----------|--------|
| [001](docs/adr/001-deterministic-rag-and-bounded-agents.md) | Deterministic hybrid-RAG for Q&A; bounded LangGraph agents for research only | Accepted |
| [002](docs/adr/002-supabase-persistent-platform.md) | Supabase for Auth, Postgres, pgvector, Storage, and RLS | Accepted |
| [003](docs/adr/003-redis-dramatiq-background-execution.md) | Redis + Dramatiq for background jobs (not PGMQ) | Provisional |
| [004](docs/adr/004-queue-port-and-transactional-outbox.md) | Queue port + transactional outbox for at-least-once delivery | Accepted |
| [005](docs/adr/005-postgres-authoritative-job-state.md) | PostgreSQL as authoritative job state store | Accepted |
| [006](docs/adr/006-hybrid-retrieval-baseline.md) | Dense + lexical + RRF fusion as retrieval baseline | Accepted |
| [007](docs/adr/007-evaluation-gated-advanced-retrieval.md) | Advanced retrieval strategies unlocked by evaluation scores only | Accepted |
| [008](docs/adr/008-capability-profiles.md) | Capability profiles for model selection | Accepted |
| [009](docs/adr/009-versioned-index-activation.md) | Versioned index activation | Accepted |
| [010](docs/adr/010-tool-approval-and-idempotency.md) | Human approval gate and idempotency key on all agent tool calls | Accepted |
| [011](docs/adr/011-api-worker-graph-boundaries.md) | API, worker, and LangGraph boundary constraints | Accepted |
| [012](docs/adr/012-langgraph-checkpoint-security.md) | LangGraph checkpoint security | Provisional |

---

## Further reading

- [Local development runbook](docs/runbooks/local-development.md)
- [Credentials and services](docs/configuration/credentials-and-services.md)
- [Canonical architecture plan](docs/architecture/rag-agent-plan.md)
- [ADR index](docs/adr/README.md)
