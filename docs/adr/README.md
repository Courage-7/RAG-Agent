# Architecture decision records

These records turn the canonical architecture into implementation constraints. `Accepted` decisions apply now; `Provisional` decisions apply to the foundation spike and must pass their stated validation gate before production.

| ADR | Decision | Status |
| --- | --- | --- |
| [001](001-deterministic-rag-and-bounded-agents.md) | Deterministic RAG and bounded agents | Accepted |
| [002](002-supabase-persistent-platform.md) | Supabase persistent platform | Accepted |
| [003](003-redis-dramatiq-background-execution.md) | Redis and Dramatiq background execution | Provisional |
| [004](004-queue-port-and-transactional-outbox.md) | Queue port and transactional outbox | Accepted |
| [005](005-postgres-authoritative-job-state.md) | PostgreSQL authoritative job state | Accepted |
| [006](006-hybrid-retrieval-baseline.md) | Hybrid retrieval baseline | Accepted |
| [007](007-evaluation-gated-advanced-retrieval.md) | Evaluation-gated advanced retrieval | Accepted |
| [008](008-capability-profiles.md) | Capability profiles | Accepted |
| [009](009-versioned-index-activation.md) | Versioned index activation | Accepted |
| [010](010-tool-approval-and-idempotency.md) | Tool approval and idempotency | Accepted |
| [011](011-api-worker-graph-boundaries.md) | API, worker, and graph boundaries | Accepted |
| [012](012-langgraph-checkpoint-security.md) | LangGraph checkpoint security | Provisional |

Superseding a record requires a new ADR that links to the old one. Do not silently edit an accepted decision's meaning.
