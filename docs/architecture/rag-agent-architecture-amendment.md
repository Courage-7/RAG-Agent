# RAG Agent Architecture Amendment

> **Status:** Reviewed and merged into [rag-agent-plan.md](./rag-agent-plan.md) on August 29, 2026. This file is retained as decision history; the merged plan is canonical and includes several reliability corrections identified during review. Its instructions to preserve `v1/` were superseded when the user explicitly authorized removal of the obsolete prototype on August 29, 2026.

## Purpose

This document amends the existing **RAG Agent Implementation Plan** rather than replacing it.

The original plan remains the baseline architecture. The goal of this amendment is to lock in several additional architectural decisions before implementation begins, especially around:

- background job execution,
- Redis,
- worker orchestration,
- provider abstractions,
- observability,
- retrieval escalation,
- infrastructure boundaries,
- and avoiding unnecessary Supabase coupling.

The original architecture already has the correct overall direction:

- deterministic hybrid-RAG for normal document Q&A,
- bounded LangGraph agent execution for research and external tools,
- Supabase for Auth, Postgres, pgvector, Storage, and RLS,
- Composio for connected third-party applications,
- Docling for document parsing,
- FastAPI for the API boundary,
- evaluation-driven introduction of advanced RAG techniques,
- asynchronous ingestion outside the HTTP request lifecycle,
- strong provenance, citations, tenant isolation, and human approval for side effects.

Do **not** discard or redesign those foundations.

---

# 1. Primary Architecture Decision: Replace Supabase Queues

The previous plan used:

```text
Supabase Queues / PGMQ
```

for document-ingestion jobs.

That decision is changed.

The initial background-job stack will be:

```text
Redis
+
Dramatiq
```

## Why

Supabase already has major responsibilities:

```text
Supabase
├── Authentication
├── PostgreSQL
├── pgvector
├── Storage
└── Row Level Security
```

We do not want to couple every infrastructure concern to Supabase.

Redis gives us a separate infrastructure layer for transient coordination while keeping durable application state in PostgreSQL.

Dramatiq provides a lightweight Python-native distributed worker framework without introducing the additional complexity of Celery at this stage.

Redis and Dramatiq can both be self-hosted during development without SaaS subscription costs.

---

# 2. Infrastructure Responsibilities

The architecture must keep responsibilities explicit.

## Supabase

Supabase remains responsible for:

```text
Auth
PostgreSQL
pgvector
RLS
Storage
application state
document metadata
document versions
chunks
conversations
tool metadata
audit records
ingestion job state
```

Supabase must **not** become the background queue.

---

## Redis

Redis is responsible for transient infrastructure concerns:

```text
background job broker
short-lived caching
distributed locks
rate limiting
deduplication keys
temporary coordination
optional short-lived progress information
```

Redis is **not** authoritative application storage.

Application state must survive complete Redis loss.

---

## Dramatiq

Dramatiq is responsible for:

```text
background job execution
worker concurrency
retry dispatch
queue routing
worker lifecycle
```

Dramatiq must **not** become the AI orchestration layer.

---

## LangGraph

LangGraph is responsible for AI/workflow orchestration:

```text
deterministic RAG graph
bounded research agent graph
tool execution state
human-in-the-loop interrupts
agent state
bounded reasoning/retrieval loops
```

LangGraph must **not** be used as the system job queue.

---

## FastAPI

FastAPI remains responsible for:

```text
HTTP API
authentication boundary
request validation
SSE streaming
CRUD
job submission
RAG invocation
agent invocation
status endpoints
```

Heavy parsing, OCR, chunking, embedding, indexing, and other long-running operations must not execute in the HTTP request lifecycle.

---

# 3. Three Different Forms of Orchestration

These concepts must not be conflated.

```text
HTTP ORCHESTRATION
FastAPI
    │
    ├── request validation
    ├── authentication
    ├── API contracts
    └── streaming


AI ORCHESTRATION
LangGraph
    │
    ├── deterministic RAG graph
    ├── evidence grading
    ├── retrieval escalation
    ├── research/tool agent
    └── human approvals


BACKGROUND EXECUTION
Dramatiq
    │
    ▼
Redis
    │
    ├── ingestion
    ├── embeddings
    ├── maintenance
    └── long-running background jobs
```

These boundaries should be visible in the codebase.

---

# 4. Updated Ingestion Architecture

Replace the previous queue implementation with:

```text
Client
  │
  ▼
Signed / resumable upload
  │
  ▼
Private Supabase Storage
  │
  ▼
FastAPI
  │
  ├── create document
  ├── create immutable document_version
  ├── create ingestion_job
  └── publish background job
          │
          ▼
       JobQueue
          │
          ▼
   Redis + Dramatiq
          │
          ▼
    Ingestion Worker
          │
          ├── validate
          ├── malware / file policy checks
          ├── Docling parse
          ├── normalize
          ├── structure-aware chunk
          ├── contextual enrichment
          ├── embed
          ├── index
          ├── verify
          └── activate document version
                  │
                  ▼
       Supabase Postgres + pgvector
```

---

# 5. Queue Abstraction Is Mandatory

Application/domain logic must not directly depend on Redis or Dramatiq APIs.

Introduce a queue port such as:

```python
from typing import Protocol

class JobQueue(Protocol):
    async def enqueue(
        self,
        queue: str,
        payload: dict,
    ) -> str:
        ...

    async def cancel(
        self,
        job_id: str,
    ) -> None:
        ...
```

The exact interface can evolve, but infrastructure-specific queue operations must stay behind an adapter.

Example:

```text
rag_core/
└── jobs/
    ├── domain/
    ├── services/
    └── ports/
        └── queue.py

rag_worker/
└── infrastructure/
    └── queues/
        └── dramatiq_redis.py
```

The application should express:

```python
queue.enqueue("document-ingestion", payload)
```

rather than:

```python
redis.rpush(...)
```

This ensures that Redis/Dramatiq could later be replaced with:

- RabbitMQ,
- Celery,
- Temporal,
- SQS,
- NATS,
- another managed queue,

without rewriting the ingestion domain.

---

# 6. `ingestion_jobs` Remains the Source of Truth

The database and queue have different responsibilities.

The queue means:

> Work is available for a worker.

The `ingestion_jobs` table means:

> This is the authoritative state of the operation.

The queue should contain only a small transport payload.

Example:

```json
{
  "job_id": "job_123",
  "document_version_id": "version_456",
  "operation": "ingest"
}
```

The worker loads the authoritative job and document state from PostgreSQL.

Do not place large document contents, parsed outputs, chunks, or application state directly into Redis messages.

---

# 7. Explicit Ingestion State Machine

Define the ingestion lifecycle before writing the worker.

Recommended state machine:

```text
QUEUED
  ↓
CLAIMED
  ↓
VALIDATING
  ↓
PARSING
  ↓
NORMALIZING
  ↓
CHUNKING
  ↓
ENRICHING
  ↓
EMBEDDING
  ↓
INDEXING
  ↓
VERIFYING
  ↓
COMPLETED
```

Failure/cancellation states:

```text
FAILED
CANCELLED
DEAD_LETTER
```

Possible additional state:

```text
RETRY_SCHEDULED
```

The database should record at minimum:

```text
current_stage
status
attempt_count
created_at
started_at
updated_at
completed_at
failed_at
failure_code
failure_message
worker_id
document_version_id
pipeline_version
```

---

# 8. Idempotency Requirements

Every ingestion operation must be safe to retry.

Use stable identity derived from:

```text
document_version
content_hash
parser_version
chunker_version
embedding_model
embedding_version
pipeline_version
```

Workers must assume duplicate delivery is possible.

Before expensive work, check whether the corresponding stage has already completed successfully.

Side effects must either:

- be naturally idempotent,
- use an idempotency key,
- or execute transactionally.

A worker crash must never leave a partially indexed document marked as active.

---

# 9. Multiple Queues

Do not place all background work into one queue.

Start with logical queue separation:

```text
Redis / Dramatiq
│
├── ingestion
│     ├── parse
│     ├── normalize
│     └── chunk
│
├── embeddings
│     └── embedding batches
│
├── maintenance
│     ├── deletion
│     ├── cleanup
│     ├── reindex
│     └── migration jobs
│
└── background-agents
      └── future long-running agent tasks
```

Initially these can share worker infrastructure.

The architecture must allow them to become separate worker deployments later.

For example:

```text
worker-ingestion
worker-embeddings
worker-maintenance
worker-agents
```

---

# 10. Adaptive RAG: Clarify the Actual Goal

The goal is **not** to blindly execute every advanced RAG technique on every request.

The goal is:

> Build an adaptive, evaluation-driven RAG platform that uses the cheapest and simplest retrieval strategy capable of producing sufficient evidence, and escalates only when necessary.

A simple request should remain simple:

```text
query
  ↓
hybrid retrieval
  ↓
reranking
  ↓
context packing
  ↓
answer
  ↓
citation verification
```

A difficult request may escalate:

```text
query
  ↓
classification
  ↓
hybrid retrieval
  ↓
evidence grading
  │
  ├── sufficient
  │      ↓
  │    answer
  │
  └── insufficient
         ↓
      query rewrite
         ↓
      decomposition
         ↓
      multi-query retrieval
         ↓
      reranking
         ↓
      evidence grading
         │
         ├── sufficient
         │      ↓
         │    answer
         │
         └── insufficient
                ↓
             web/tool research
                ↓
             synthesis
                ↓
             citation verification
```

All escalation loops must be bounded.

---

# 11. Advanced Retrieval Techniques

Keep these as feature-flagged/evaluation-gated strategies rather than baseline execution:

```text
Multi-query retrieval
RAG Fusion
Query decomposition
HyDE
Contextual Retrieval
Parent-child retrieval
Neighbor expansion
Recursive summaries
RAPTOR
GraphRAG
ColBERT / late interaction
Corrective RAG
Self-verification
```

Do not enable a technique because it is fashionable.

Enable it only if evaluation demonstrates measurable benefit on our corpus.

---

# 12. Retrieval Strategy Registry

Introduce a retrieval strategy boundary.

Example conceptual contract:

```python
class Retriever(Protocol):
    async def retrieve(
        self,
        query: RetrievalQuery,
    ) -> RetrievalResult:
        ...
```

Potential implementations:

```text
HybridRetriever
MultiQueryRetriever
DecompositionRetriever
HyDERetriever
GraphRetriever
RaptorRetriever
WebFallbackRetriever
```

The LangGraph routing layer chooses an appropriate strategy.

Retrieval implementation must remain independently testable outside the graph.

---

# 13. Model Provider Abstraction

The codebase must not hard-code one LLM provider throughout the application.

Introduce provider/model profiles.

Conceptually:

```text
ModelProfile
├── provider
├── model
├── temperature
├── max_tokens
├── timeout
├── retry_policy
├── cost_class
├── latency_class
└── capability flags
```

Possible capability flags:

```text
structured_output
tool_calling
vision
long_context
reasoning
streaming
```

The architecture should allow providers such as:

```text
OpenAI
Groq
Anthropic
Gemini
OpenRouter
local/OpenAI-compatible endpoints
```

without rewriting business logic.

Exact providers/models are configuration and evaluation decisions.

---

# 14. Embedding Abstraction

Embedding models must also be replaceable.

Do not couple chunk persistence directly to one embedding implementation.

Maintain explicit:

```text
embedding_provider
embedding_model
embedding_version
embedding_dimension
created_at
```

Never mix vector dimensions or embeddings from different incompatible models in the same index without explicit versioning.

Embedding upgrades must support:

```text
old active index
       +
parallel new index
       ↓
validation
       ↓
traffic switch
       ↓
old index retirement
```

---

# 15. Reranker Abstraction

The reranker must be independently replaceable and benchmarkable.

Conceptually:

```python
class Reranker(Protocol):
    async def rerank(
        self,
        query: str,
        candidates: list[RetrievedChunk],
    ) -> list[RankedChunk]:
        ...
```

This allows evaluation of:

```text
cross-encoder rerankers
API rerankers
LLM-based reranking
no-reranker baseline
```

without modifying retrieval orchestration.

---

# 16. Redis Caching Strategy

Redis may additionally provide **safe transient caching**.

Potential caches:

```text
query normalization
embedding lookup
retrieval candidates
reranker results
web-search results
tool schemas
rate limits
short-lived model/provider metadata
```

Do not cache security decisions.

Every cache key involving user-visible data must include appropriate isolation dimensions such as:

```text
workspace_id
knowledge_base_id
user/permission scope where required
document version
retrieval configuration version
```

Cache invalidation must be tied to document/index/version changes.

---

# 17. Observability Requirements

Observability must span the full request/job lifecycle.

Every operation should carry:

```text
trace_id
request_id
job_id
conversation_id
workspace_id
document_id
document_version_id
```

where applicable.

Track at minimum:

## API

```text
request latency
TTFT
response duration
status
stream disconnects
```

## Queue

```text
queue depth
enqueue rate
claim latency
job age
retry rate
dead-letter rate
worker concurrency
```

## Ingestion

```text
validation duration
parse duration
page count
chunk count
chunking duration
embedding batches
embedding token count
embedding duration
indexing duration
verification duration
failed stage
total ingestion duration
```

## Retrieval

```text
dense latency
lexical latency
candidate count
RRF contribution
reranker latency
Recall@k
MRR
nDCG
selected context count
context token count
```

## LLM

```text
provider
model
latency
TTFT
input tokens
output tokens
estimated cost
retry count
fallback count
```

## Agent

```text
tool calls
tool failures
approval requests
trajectory length
model calls
budget consumption
termination reason
```

Use structured logging and OpenTelemetry-compatible tracing.

LangSmith can be used where useful for LangGraph/RAG evaluation and model/tool traces, but domain telemetry should not depend exclusively on LangSmith.

---

# 18. Error Taxonomy

Do not rely on generic `Exception` handling.

Define typed error classes / error codes for categories such as:

```text
authentication_error
authorization_error
invalid_upload
unsupported_document
malware_rejected
storage_error
queue_unavailable
worker_timeout
document_parse_failed
chunking_failed
embedding_provider_error
embedding_rate_limited
indexing_failed
retrieval_failed
reranker_failed
insufficient_evidence
model_provider_error
tool_error
tool_permission_error
approval_required
approval_rejected
budget_exceeded
deadline_exceeded
```

Failures exposed through APIs must be typed and safe.

Internal traces can retain richer diagnostic information.

---

# 19. Timeouts, Retries, and Budgets

Every external operation must define:

```text
timeout
retry policy
max attempts
backoff
idempotency characteristics
```

Retries should only occur for classified transient errors.

Do not automatically retry destructive or side-effecting tool operations unless an idempotency contract exists.

Agent runs must have bounded:

```text
model calls
tool calls
retrieval attempts
elapsed time
token usage
cost
```

No unrestricted reflection or recursive agent loops.

---

# 20. Updated Worker Deployment Boundary

The FastAPI Cloud application should serve requests.

Heavy workers should run separately.

Development:

```text
Docker Compose
├── API
├── Redis
├── Dramatiq worker
└── supporting local services
```

Production worker hosting must remain portable.

Potential future worker runtimes include:

```text
VM/container host
managed container service
Kubernetes
dedicated CPU worker
dedicated GPU worker
```

Do not make the ingestion implementation depend on FastAPI Cloud-specific worker behavior.

---

# 21. Zero-Cost / Low-Cost Development Principle

During development, prioritize infrastructure that can run locally without paid SaaS requirements.

Preferred local stack:

```text
Docker / Docker Compose
Redis
Dramatiq
local Supabase development stack where appropriate
local Postgres/pgvector
FastAPI
Docling
```

Do not introduce paid infrastructure merely to satisfy an architectural pattern.

However, do **not** compromise production portability.

Infrastructure must remain replaceable through ports/adapters.

---

# 22. Updated Repository Structure

Retain the general `uv` workspace approach, but make infrastructure boundaries more explicit.

Recommended direction:

```text
.
├── apps/
│   ├── api/
│   │   └── src/rag_api/
│   │
│   └── worker/
│       └── src/rag_worker/
│           ├── consumers/
│           ├── tasks/
│           └── infrastructure/
│
├── packages/
│   └── core/
│       └── src/rag_core/
│           ├── agents/
│           ├── auth/
│           ├── ingestion/
│           ├── retrieval/
│           │   ├── strategies/
│           │   ├── reranking/
│           │   └── grading/
│           ├── jobs/
│           │   ├── domain/
│           │   └── ports/
│           ├── models/
│           ├── embeddings/
│           ├── tools/
│           ├── policies/
│           └── observability/
│
├── infrastructure/
│   ├── redis/
│   └── docker/
│
├── supabase/
│   ├── migrations/
│   ├── seed.sql
│   └── tests/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── security/
│   ├── contract/
│   └── failure/
│
├── evals/
│   ├── datasets/
│   ├── evaluators/
│   ├── baselines/
│   └── experiments/
│
├── docs/
│   ├── architecture/
│   ├── adr/
│   └── runbooks/
│
├── docker-compose.yml
├── pyproject.toml
├── uv.lock
└── README.md
```

This is directional. Preserve feature-based cohesion and avoid unnecessary directory fragmentation.

---

# 23. Architecture Decision Records to Add

Before implementation, create ADRs for at least:

```text
ADR-001: Deterministic RAG vs bounded agent execution
ADR-002: Supabase as primary persistent data platform
ADR-003: Redis + Dramatiq for background execution
ADR-004: Queue abstraction / infrastructure portability
ADR-005: PostgreSQL ingestion_jobs as authoritative job state
ADR-006: Hybrid retrieval baseline
ADR-007: Evaluation-gated advanced retrieval
ADR-008: Model/provider abstraction
ADR-009: Embedding versioning strategy
ADR-010: Human approval policy for side-effecting tools
ADR-011: Worker/API deployment separation
```

Keep ADRs concise and decision-oriented.

---

# 24. Changes Required in the Existing Plan

Update the existing architecture document as follows.

## Replace

```text
Supabase Queues / PGMQ
```

with:

```text
Redis + Dramatiq
```

where it refers to the concrete ingestion queue implementation.

Do **not** replace generic references to a "durable queue" where the abstraction is intentional.

---

## Add

A queue abstraction section documenting:

```text
JobQueue port
Redis/Dramatiq adapter
PostgreSQL as authoritative job state
```

---

## Add

The explicit ingestion state machine.

---

## Add

The three orchestration boundaries:

```text
FastAPI = HTTP orchestration
LangGraph = AI orchestration
Dramatiq = background execution
```

---

## Add

Provider abstractions for:

```text
LLMs
embeddings
rerankers
retrieval strategies
```

---

## Add

Redis cache/coordination responsibilities.

---

## Add

Cross-system trace propagation.

---

# 25. What NOT to Implement Yet

Do not prematurely build:

```text
Kafka
RabbitMQ
Temporal
Kubernetes
GraphRAG
RAPTOR
ColBERT
multiple embedding indexes
multiple model providers
complex autoscaling
GPU infrastructure
custom distributed scheduler
```

unless the architecture requires a minimal interface for future support.

The current milestone is foundation, contracts, evaluation setup, and clean boundaries.

Advanced components come only after the baseline system is measurable.

---

# 26. Revised Milestones

## Milestone 0 — Architecture and Evaluation Foundation

- Preserve the existing v1 prototype as archive/reference.
- Update the main architecture document with this amendment.
- Add ADRs.
- Define benchmark/evaluation datasets.
- Define latency, quality, cost, and safety metrics.
- Define provider contracts.
- Define queue/job contracts.
- Define ingestion state machine.
- Establish baseline retrieval experiments.

---

## Milestone 1 — Project Foundation

- Create/confirm the `uv` workspace.
- Create FastAPI application skeleton.
- Create worker application skeleton.
- Add Redis to Docker Compose.
- Add Dramatiq.
- Implement queue port + Redis/Dramatiq adapter.
- Add structured settings.
- Add logging/tracing baseline.
- Add health/readiness endpoints.
- Add CI baseline.
- Add local development documentation.

Do **not** build the full RAG pipeline yet.

---

## Milestone 2 — Identity and Tenant Isolation

Continue the original plan:

- Supabase OTP authentication.
- JWT verification.
- workspace model.
- RLS.
- storage policies.
- security tests.
- tenant-boundary tests.

---

## Milestone 3 — Durable Ingestion

Implement:

- signed/resumable uploads,
- document and version lifecycle,
- `ingestion_jobs`,
- Redis/Dramatiq dispatch,
- Docling parsing,
- structure-aware chunking,
- embedding abstraction,
- indexing,
- verification,
- retries,
- dead-letter handling,
- cancellation,
- reindexing,
- deletion,
- stage observability.

---

## Milestone 4+ — Continue Existing Plan

Proceed with:

- production hybrid RAG,
- citations,
- evidence grading,
- abstention,
- LangGraph agent path,
- Composio,
- approvals,
- advanced retrieval experiments,
- production hardening.

---

# 27. Non-Negotiable Architecture Principles

The implementation must preserve the following principles:

1. **The model never decides authorization.**
2. **Redis is transient infrastructure, not the source of truth.**
3. **PostgreSQL owns durable application/job state.**
4. **LangGraph is not the background queue.**
5. **Dramatiq is not the AI reasoning/orchestration engine.**
6. **FastAPI requests do not perform heavy ingestion work.**
7. **Every background job must be idempotent.**
8. **Every agent/retrieval loop must be bounded.**
9. **Every important factual answer must be grounded in evidence.**
10. **Advanced RAG techniques are enabled through evaluation, not enthusiasm.**
11. **Side-effecting tools require deterministic policy enforcement and appropriate approval.**
12. **Infrastructure providers must be replaceable where practical.**
13. **Tenant isolation is a release-blocking invariant.**
14. **Observability is part of the architecture, not an afterthought.**
15. **The simplest retrieval path that produces sufficient evidence should win.**

---

# 28. Immediate Instruction to the Coding Agent

Do not start implementing advanced RAG features yet.

First:

1. Review the existing architecture plan together with this amendment.
2. Update the existing architecture document rather than replacing it.
3. Identify every section that still directly assumes Supabase Queues / PGMQ.
4. Replace the concrete queue decision with Redis + Dramatiq.
5. Introduce the queue abstraction.
6. Define the ingestion state machine.
7. Define the worker/API/LangGraph responsibility boundaries.
8. Add the required ADRs.
9. Update repository structure only where needed to support these boundaries.
10. Produce a concise implementation checklist for Milestones 0 and 1.
11. Flag contradictions between this amendment and the existing codebase/plan before making invasive changes.
12. Do not modify archived `v1` implementation unless explicitly instructed.

After completing the architecture/documentation changes, provide:

```text
- changed files
- architecture decisions made
- unresolved decisions
- implementation checklist
- risks
- assumptions
```

Do not begin Milestone 2 or later until Milestones 0 and 1 have a clean foundation.

---

# Final Target

The target is not merely "a RAG chatbot."

The target is a:

> **multi-tenant, adaptive, evaluation-driven RAG and agent platform with hybrid retrieval, verifiable provenance, bounded agent execution, durable asynchronous ingestion, external tool connectivity, provider portability, strong tenant isolation, and measurable quality/performance characteristics.**

The architecture should remain sophisticated where sophistication provides measurable value, and deliberately simple where additional machinery would only increase cost, latency, coupling, or operational burden.
