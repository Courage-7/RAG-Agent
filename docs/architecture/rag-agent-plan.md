# RAG Agent Implementation Plan

**Research date:** August 29, 2026

**Status:** Canonical proposed architecture and implementation plan

**Amendment status:** Reviewed and incorporated on August 29, 2026

The recommended rebuild is a multi-tenant, evaluation-driven RAG platform with two execution modes:

1. A deterministic hybrid-RAG path for ordinary document Q&A.
2. A bounded LangGraph agent path for research, web search, calendar, and other Composio tools.

This architecture is more reliable than routing every request through an open-ended autonomous agent.

Groq is the primary LLM inference provider. The application integrates through `langchain-groq`/`ChatGroq`, while model aliases and capability profiles prevent business logic from depending on a single Groq model ID.

## Canonical decision summary

This document is the single implementation plan. It incorporates the accepted parts of `rag-agent-architecture-amendment.md`; the amendment remains as decision history, but implementation should follow this document when wording differs.

The principal amended decision is to use Redis plus Dramatiq for initial background execution while keeping Supabase Postgres authoritative for all durable application and job state. This is an intentional separation of responsibilities, not a claim that Redis is intrinsically more durable than Supabase Queues. Supabase Queues remains a credible fallback because it is a durable Postgres-native queue with guaranteed delivery. Redis/Dramatiq earns its place by providing a Python worker runtime, queue routing, retries, and a reusable transient coordination layer. See [Supabase Queues](https://supabase.com/docs/guides/queues), the [Dramatiq guide](https://dramatiq.io/guide.html), and the [Dramatiq API reference](https://dramatiq.io/reference.html).

The tradeoff is an additional service, a second failure domain, a database-to-broker dual write, and more production operations. The outbox/reconciler makes that boundary recoverable but does not make it free. If the Milestone 0 spike cannot meet durability, recovery, hosting, and cost gates, PGMQ is the preferred simpler fallback rather than forcing Redis/Dramatiq for architectural aesthetics.

The choice is accepted with these mandatory safeguards:

- A PostgreSQL transactional outbox and reconciliation loop close the database-to-broker dual-write gap.
- Workers are idempotent and assume at-least-once execution and duplicate delivery.
- Redis broker data is isolated from evictable cache data by separate instances where practical, or by a shared global `noeviction` policy plus capacity limits and alerts; namespaces alone are not isolation.
- Production Redis must have an explicit persistence, high-availability, backup, TLS, and recovery posture; a free non-persistent Redis tier is development-only.
- Cancellation is authoritative in PostgreSQL and cooperative at stage boundaries. Broker-message removal is never treated as proof that work stopped.
- A Milestone 0 deployment spike must verify worker hosting, Redis/Dramatiq recovery behavior, and operating cost. The `JobQueue` port permits a documented fallback to PGMQ, RabbitMQ, SQS, or another broker without rewriting ingestion domain logic.

Redis Cloud documents that its free tier does not provide persistence, while FastAPI Cloud currently supports a Redis Cloud integration and injects `REDIS_URL`. These facts make local/free development convenient but do not satisfy the production durability gate by themselves. See [Redis Cloud persistence](https://redis.io/docs/latest/operate/rc/databases/configuration/data-persistence/) and [FastAPI Cloud Redis integration](https://fastapicloud.com/docs/integrations/redis-integration/).

### Amendment review disposition

Accepted unchanged in principle:

- Separate FastAPI HTTP orchestration, LangGraph AI orchestration, and Dramatiq background execution.
- Keep Postgres authoritative and Redis transient.
- Use queue, model, embedding, reranker, and retrieval-strategy ports.
- Make ingestion stateful, idempotent, versioned, observable, and recoverable.
- Use adaptive/evaluation-gated retrieval instead of enabling every advanced technique.
- Keep heavy workers portable and separate from the request-serving API.

Accepted with corrections:

- Redis/Dramatiq replaces PGMQ as the initial implementation, but only with an outbox/reconciler and a production durability gate.
- Queue cancellation is cooperative database state, not a reliable generic broker operation.
- `status` and `current_stage` are separate fields; leases and heartbeats recover abandoned claims.
- Initial queue names are flat and coarse-grained. Parsing, normalization, and chunking are recorded stages, not necessarily separate broker jobs.
- Broker and cache workloads are isolated so cache eviction cannot destroy pending work.
- Provider portability begins with interfaces and profiles, not simultaneous implementation of every provider.
- Trace identifiers belong in controlled logs/traces; high-cardinality tenant identifiers are not general metric labels.

The original codebase had no FastAPI, LangGraph, Supabase, Redis/Dramatiq, worker, tenant model, or new package foundation worth carrying forward. Implementation is therefore a clean workspace rebuild rather than an in-place refactor. The obsolete prototype was removed on August 29, 2026 after explicit user authorization.

### Non-negotiable invariants

1. The model never decides authorization.
2. Redis is transient infrastructure; Postgres owns durable application, job, and dispatch intent.
3. LangGraph is not the system queue, and Dramatiq is not the AI reasoning engine.
4. FastAPI requests never perform heavy ingestion work.
5. Every job and side effect is idempotent or explicitly non-retryable and reconcilable.
6. Every retrieval/agent loop has hard attempt, time, token, tool, and cost limits.
7. Important factual claims have verifiable provenance; insufficient evidence produces abstention.
8. Advanced retrieval is promoted by evaluation, not novelty.
9. Side effects pass deterministic policy and appropriate human approval.
10. Tenant isolation and zero unauthorized side effects are release-blocking invariants.
11. Observability, safe errors, recovery, deletion, and retention are part of the feature definition.
12. The simplest retrieval path that meets measured quality should win.

## Repository assessment

The removed prototype had:

- Streamlit coupled directly to retrieval and ingestion.
- Local FAISS indexes and unsafe `allow_dangerous_deserialization=True`.
- Deprecated LangChain chain/import patterns.
- Fixed character chunking with no structure, page, table, or version awareness.
- No user identity, tenant isolation, RLS, ingestion jobs, or deletion lifecycle.
- No trustworthy citation/provenance contract.
- No hybrid search or real reranking despite configuration suggesting it.
- Unpinned `requirements.txt`.
- Tests focused almost entirely on mocked query rewriting.
- Evaluation based largely on text overlap rather than retrieval, groundedness, citation, and agent behavior.

These limitations justify the clean rebuild. Historical details remain in Git history and the architecture amendment; no runtime code depends on the removed prototype.

## Current stack baseline

As researched on August 29, 2026, the stable ecosystem is substantially different from the original project:

| Component | Current stable line | Direction |
|---|---:|---|
| LangChain | 1.3.x | Modern agents, structured output, middleware |
| LangGraph | 1.2.x | Durable execution, interrupts, explicit state graphs |
| FastAPI | 0.141.x | Async API and FastAPI Cloud CLI |
| Supabase Python | 2.31.x | Auth, Storage, Data API |
| Docling | 2.121.x | Layout-aware parsing, OCR, tables, structured chunks |
| Dramatiq | 2.2.x | Distributed workers, routing, bounded retries |
| Redis | Deployment-selected | Broker, cache, locks, rate limits, transient coordination |
| GroqCloud | Primary LLM provider | Fast chat/reasoning inference, structured output, streaming, and tool calling |

Sources: [LangChain PyPI](https://pypi.org/project/langchain/), [LangGraph PyPI](https://pypi.org/project/langgraph/), [FastAPI PyPI](https://pypi.org/project/fastapi/), [Supabase Python PyPI](https://pypi.org/project/supabase/), [Docling PyPI](https://pypi.org/project/docling/), [Dramatiq documentation](https://dramatiq.io/), and [Groq supported models](https://console.groq.com/docs/models).

Target Python 3.12 initially for broad compatibility with document-processing and optional GraphRAG packages. Exact versions will be compatibility-tested and committed through `uv.lock`, not installed as floating dependencies. `uv sync --locked` is the reproducible CI/deployment path recommended by the current [`uv` documentation](https://docs.astral.sh/uv/concepts/projects/sync/).

Current Supabase migration notes: hosted projects now ignore explicitly pinned Postgres extension versions, so migrations use `create extension ...`/`alter extension ... update` without a version clause and CI verifies the actual available pgvector behavior. Recent self-hosted defaults also moved to Postgres 17 and Envoy, reinforcing that local/CI images must be deliberately pinned and upgrade-tested rather than assumed. Supabase free-tier Auth email-template customization is restricted for new projects, so production passwordless email already requires the planned custom SMTP path. See the [extension-version change](https://supabase.com/changelog/extension-version-pinning-ignored) and [Supabase breaking-change changelog](https://supabase.com/changelog?types=breaking-change).

## Target architecture

```text
Web or mobile client
        │
        │ Supabase access token
        ▼
FastAPI API — FastAPI Cloud
        │
        ├── JWT verification / tenant context
        ├── CRUD APIs
        ├── SSE response streaming
        ├── job submission through JobQueue port
        └── LangGraph AI orchestrator
                │
                ├── deterministic RAG workflow
                ├── bounded research/tool agent
                └── human-approval interrupts
                        │
          ┌─────────────┼───────────────────┐
          ▼             ▼                   ▼
  Supabase RAG      Composio sessions    Web search
  retrieval RPC     and app tools        provider
          │             │
          ▼             ▼
 Postgres/pgvector   Calendar, email,
 Storage, Auth       Drive, Slack, etc.

Upload → private Storage → Postgres job + outbox → Redis/Dramatiq → worker
                          authoritative state                       │
                                                        parse/chunk/embed/index
```

LangGraph is appropriate because it provides durable execution, persistence, streaming, and human-in-the-loop, while LangChain provides models, tools, middleware, and structured output. See the [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview).

## System boundaries and three forms of orchestration

The codebase must keep HTTP orchestration, AI orchestration, and background execution distinct:

| Boundary | Owns | Must not own |
|---|---|---|
| FastAPI | HTTP validation, authentication, CRUD, SSE, job submission, request deadlines | Heavy OCR/embedding work or open-ended background processing |
| LangGraph | RAG routing, evidence grading, bounded agent loops, tool state, durable approval interrupts | The system job queue or tenant authorization decisions |
| Dramatiq | Worker concurrency, queue routing, retry dispatch, worker lifecycle | AI reasoning, retrieval policy, or durable application state |
| Redis | Broker transport, short-lived cache, rate limits, locks, deduplication, coordination | Authoritative job, user, document, or conversation state |
| Supabase | Auth, Postgres, pgvector, RLS, Storage, durable metadata, audit and job state | Worker lifecycle |

LangGraph runtime checkpoints for resumable agent runs and approval interrupts live in a dedicated Postgres schema with explicit retention and access controls. They are workflow state, not a replacement for domain tables such as `conversations`, `messages`, `tool_runs`, or `approval_requests`.

## 1. RAG request path

Every request receives a typed graph state containing:

- `request_id`
- `user_id`
- `workspace_id`
- `conversation_id`
- Normalized query
- Intent and freshness requirements
- Retrieval strategy
- Evidence and scores
- Tool-call and token budgets
- Approval state
- Citations
- Final answer or abstention reason

The graph:

```text
authenticate
    ↓
normalize and classify request
    ↓
choose route
    ├── direct conversational response
    ├── deterministic internal RAG
    └── agentic research/tool workflow
                  ↓
        retrieve candidate evidence
                  ↓
        fuse, deduplicate, rerank
                  ↓
          grade evidence quality
          ├── sufficient → answer
          └── insufficient
                ├── rewrite/decompose once
                ├── optional web fallback
                └── abstain
                  ↓
        claim and citation verification
                  ↓
         structured streamed response
```

Important constraints:

- Maximum retrieval attempts, model calls, tool calls, elapsed time, and cost per run.
- No infinite reflection loop.
- Side-effecting tools never retry automatically unless they have an idempotency key.
- Retrieval or tool content is always treated as untrusted data, never as system instruction.
- Authorization is deterministic application logic; the model never decides what a user may access.
- The system answers “I do not have enough evidence” instead of fabricating.
- Every significant factual claim must link to a source span.

LangChain’s current agentic-RAG example uses retrieval grading and query rewriting. We will make those components explicit, bounded, and independently testable. See [LangGraph agentic RAG](https://docs.langchain.com/oss/python/langgraph/agentic-rag).

## 2. Retrieval design

### Production baseline

The first production retriever should contain:

1. Query normalization and language detection.
2. Mandatory workspace, knowledge-base, and document ACL filters.
3. Dense vector search in pgvector.
4. PostgreSQL full-text search for identifiers and exact terminology.
5. Reciprocal Rank Fusion of dense and lexical results.
6. Deduplication and diversity selection.
7. Cross-encoder or API reranking.
8. Parent/neighbor expansion to restore local context.
9. Token-budgeted context packing.
10. Evidence grading and abstention.
11. Exact page, section, table, and span citations.

Supabase documents this same Postgres foundation: `tsvector`/GIN for lexical search, pgvector/HNSW for semantic search, and rank fusion to combine them. Supabase recommends HNSW for production vector indexes. See [Supabase hybrid search](https://supabase.com/docs/guides/ai/hybrid-search) and [going to production with pgvector](https://supabase.com/docs/guides/ai/going-to-prod).

Implement the hybrid query as a controlled Postgres RPC rather than depend on a thin `SupabaseVectorStore` abstraction. This provides:

- RRF tuning.
- ACL and metadata filters inside the query.
- Query-level observability.
- Stable result and citation schemas.
- Independent dense, lexical, and fused scores.
- Easier index and SQL optimization.

### Adaptive retrieval contract

The target is adaptive RAG, not maximum machinery on every request. The system starts with the cheapest strategy likely to produce sufficient evidence and escalates only when a typed evidence grader says it is necessary:

```text
hybrid retrieval → rerank → pack → grade
                                  ├── sufficient → answer + verify citations
                                  └── insufficient
                                         → one rewrite/decomposition pass
                                         → optional multi-query or specialized strategy
                                         → grade again
                                               ├── sufficient → answer
                                               └── web/tool research or abstain
```

All branches share hard limits for attempts, candidates, context tokens, elapsed time, model calls, and cost. Strategy selection and evidence grading are logged so evaluations can compare the chosen path with a simpler baseline.

Retrieval lives behind an independently testable strategy registry. Its input must make the security scope impossible to omit:

```python
class Retriever(Protocol):
    async def retrieve(self, query: RetrievalQuery) -> RetrievalResult: ...

# RetrievalQuery includes the normalized query, workspace and knowledge-base
# scope, verified principal/authorization fingerprint, filters, limits,
# freshness requirements, and retrieval-configuration version.
```

Initial registered implementations are `HybridRetriever` and `WebFallbackRetriever`. Later candidates include `MultiQueryRetriever`, `DecompositionRetriever`, `HyDERetriever`, `RaptorRetriever`, and `GraphRetriever`. Authorization filters execute inside the database retrieval operation; post-filtering an unauthorized candidate set is forbidden.

### Advanced techniques introduced through evaluations

These should be feature-flagged experiments rather than activated together:

- Multi-query or RAG-fusion for ambiguous questions.
- Query decomposition for multi-hop questions.
- HyDE for domains where user wording differs sharply from document wording.
- Contextual chunk enrichment at ingestion.
- Parent-child and recursive summaries for long documents.
- RAPTOR-style tree retrieval for long-form and multi-step reasoning.
- GraphRAG for whole-corpus themes, entity relationships, and global questions.
- ColBERT/late-interaction retrieval if dense plus reranking still misses fine-grained evidence.
- Corrective RAG: use retrieval quality to decide whether to rewrite, search the web, or abstain.
- Self-reflection only as a verifier, not an unrestricted model loop.

An experiment is promoted only when a versioned evaluation demonstrates a material improvement over the current baseline without violating latency, cost, citation, or security gates. An experiment must also have a rollback flag and record which knowledge bases or query classes it serves. GraphRAG, RAPTOR, ColBERT, and multiple simultaneous embedding indexes are specifically deferred beyond the foundation milestones.

Contextual Retrieval combines contextualized lexical and semantic indexes with reranking. Anthropic reported materially lower retrieval failure rates in its evaluations, but this must be reproduced on our own corpus. See [Contextual Retrieval](https://www.anthropic.com/engineering/contextual-retrieval).

RAPTOR improves long-document reasoning with recursively clustered summaries, while Microsoft GraphRAG targets local entity questions and expensive whole-dataset aggregation. Both solve narrower problems and should be enabled per knowledge base, not imposed on every upload. See the [RAPTOR paper](https://arxiv.org/abs/2401.18059) and [Microsoft GraphRAG query modes](https://microsoft.github.io/graphrag/query/overview/).

## 3. Document ingestion

Uploads should never be fully processed inside a FastAPI request.

1. Client requests a signed/resumable upload.
2. File uploads directly to a private Supabase Storage bucket.
3. In one Postgres transaction, the API creates the document/version, an `ingestion_jobs` row, and an outbox event.
4. A dispatcher publishes the small outbox payload through the `JobQueue` port to Redis/Dramatiq and marks the outbox event dispatched.
5. A reconciliation process republishes undispatched events and stale runnable jobs after broker or dispatcher failure.
6. A worker receives a job identifier and loads authoritative job, document, policy, and version state from Postgres.
7. The worker claims the job with a lease and heartbeat, then checks for cancellation and prior stage completion.
8. The worker validates MIME type, extension, size, checksum, decompression limits, and malware/file policy.
9. Docling extracts document hierarchy, reading order, pages, headings, tables, formulas, and OCR.
10. Normalized Docling JSON and Markdown are written back to private Storage.
11. Structure-aware, tokenizer-aware chunks are produced.
12. Original display text and context-enriched embedding text are stored separately.
13. Chunks are embedded in bounded batches and staged under the immutable version.
14. Verification checks artifact counts, required metadata, vector dimensions, index visibility, and citation anchors.
15. A transaction activates the new version only after verification; old versions retire asynchronously.
16. The worker records completion, emits telemetry, and acknowledges the transport message.

Docling’s hybrid chunker respects document hierarchy and token limits, enriches chunks with metadata, and can repeat table headers across table chunks. See [Docling chunking](https://docling-project.github.io/docling/concepts/chunking/).

### Queue port, outbox, and recovery

Domain and application code must not call Redis or Dramatiq directly. The initial adapter implements a narrow port:

```python
class JobQueue(Protocol):
    async def enqueue(self, envelope: JobEnvelope) -> DispatchReceipt: ...
```

`JobEnvelope` contains identifiers and routing metadata only, normally `job_id`, `operation`, `schema_version`, `trace_context`, and an idempotency key. Documents, parsed outputs, chunks, secrets, authorization objects, and other application state never travel in the message.

Creating a database job and publishing a broker message cannot be one atomic transaction. The transactional outbox makes the database commit authoritative and publishing replayable:

```text
Postgres transaction: ingestion_job + job_dispatch_outbox
                              ↓
dispatcher publishes to Redis/Dramatiq
                              ↓
worker loads and conditionally claims ingestion_job
                              ↓
reconciler republishes undispatched/stale runnable work
```

Delivery is treated as at least once. Duplicate dispatch is expected and harmless. Redis loss may delay work, but cannot erase authoritative job intent; restoring Redis and running reconciliation reconstructs runnable messages from Postgres.

Do not expose a generic `cancel(message_id)` guarantee in the queue port. The cancellation endpoint writes `cancel_requested_at`, actor, and reason in Postgres. Workers cooperatively stop at safe stage/batch boundaries, leave staged data inactive, and record `CANCELLED`. Any broker abort or message removal is optional best effort only.

### Ingestion state machine

```text
QUEUED → CLAIMED → VALIDATING → PARSING → NORMALIZING → CHUNKING
       → ENRICHING → EMBEDDING → INDEXING → VERIFYING → COMPLETED

Any runnable stage → RETRY_SCHEDULED → CLAIMED
Any nonterminal stage → CANCELLED
Retries exhausted or permanent failure → FAILED or DEAD_LETTER
```

The exact model separates `status` from `current_stage`; this avoids encoding every stage/status combination in one enum. Required fields include `attempt_count`, `max_attempts`, `lease_expires_at`, `heartbeat_at`, timestamps, `failure_code`, a sanitized `failure_message`, `worker_id`, `pipeline_version`, `idempotency_key`, `cancel_requested_at`, and the document-version identifier. State changes use conditional updates or row locks so only the lease owner may advance active work. A sweeper recovers expired claims.

Each job is idempotent over the document version, content hash, parser version, chunker version, enrichment version, embedding provider/model/version, and pipeline version. Each expensive stage records a durable artifact/checkpoint before advancing. Side effects are naturally idempotent, keyed, or transactional. A worker crash can never make a partially indexed version active.

Dramatiq automatically retries failed actors unless configured otherwise and assumes actors are idempotent. We will override its broad defaults with explicit `max_retries`, backoff, retry classification, time limits, and retry-exhausted handling per actor. See [Dramatiq error handling](https://dramatiq.io/guide.html#error-handling) and [Retries middleware](https://dramatiq.io/reference.html#dramatiq.middleware.Retries).

### Queue topology and Redis isolation

Start with three flat logical queues, not a task-per-stage distributed workflow:

- `ingestion`: one orchestration actor advances parsing through verification with durable stage checkpoints.
- `embeddings`: optional bounded embedding batches when evaluation shows separate scaling is useful.
- `maintenance`: deletion, cleanup, reindex, repair, and migration jobs.

Reserve `background-agents` for a later evaluated requirement. Initially the queues may share one worker deployment, while configuration allows distinct concurrency and later separate CPU/GPU deployments.

Broker keys must use a non-evicting Redis deployment or isolated instance with a documented persistence/HA configuration. Cache keys may be evictable and should preferably use a separate Redis database/instance and credentials. Do not let cache pressure evict broker messages. Production readiness includes killing workers and Redis during test jobs, restoring service, running reconciliation, and proving eventual terminal state without duplicate active versions.

## 4. Supabase data model

Core application tables:

- `profiles`
- `workspaces`
- `workspace_members`
- `knowledge_bases`
- `knowledge_base_members`
- `documents`
- `document_versions`
- `chunks`
- `chunk_embeddings`
- `ingestion_jobs`
- `job_dispatch_outbox`
- `conversations`
- `messages`
- `answer_sources`
- `composio_sessions`
- `tool_connections`
- `tool_runs`
- `approval_requests`
- `feedback`
- `evaluation_cases`
- `audit_events`

Important chunk fields:

- Tenant/workspace and knowledge-base identifiers.
- Document and immutable document-version identifiers.
- Original text.
- Context-enriched embedding text.
- `tsvector` field.
- Page number, heading path, table/figure identifiers, and source offsets.
- Token count and ordinal.
- Content and pipeline hashes.
- Parser, chunker, and embedding model versions.
- Visibility/ACL metadata.

Embedding records include provider, model, version, dimension, vector, timestamps, and the source/pipeline hash. Because a pgvector column has a declared dimension and each index must be compatible with it, upgrades use an explicit parallel table/partition/index or another migration-safe physical layout. Vectors from different models, versions, or dimensions are never silently queried together. The active embedding profile is versioned per knowledge base; activation occurs only after coverage and retrieval evaluation pass.

`ingestion_jobs` is the authoritative state of background operations. `job_dispatch_outbox` records replayable dispatch intent. Redis message state, Dramatiq results, and short-lived progress caches are not exposed as the canonical job API. Retention and cleanup policies apply independently to terminal jobs, outbox events, inactive document versions, normalized artifacts, raw uploads, audit records, conversations, and LangGraph checkpoints.

Raw originals belong in a private Storage bucket under a path such as:

```text
{workspace_id}/{knowledge_base_id}/{document_id}/{version_id}/source.pdf
```

Normalized artifacts and extracted images use separate private prefixes.

## 5. Authentication and tenant security

Use Supabase email OTP as the default login and offer a magic link as an optional alternative. Magic links can be consumed by corporate email scanners; Supabase explicitly recommends OTP or an intermediate confirmation page for this case. See [Supabase passwordless auth](https://supabase.com/docs/guides/auth/auth-email-passwordless) and [email-template limitations](https://supabase.com/docs/guides/auth/auth-email-templates).

Authentication flow:

1. Frontend calls Supabase `signInWithOtp`.
2. Production uses custom SMTP with configured rate limits.
3. Frontend receives and refreshes the Supabase session.
4. It sends the access token as `Authorization: Bearer`.
5. FastAPI validates signature, issuer, audience, and expiration against Supabase JWKS.
6. The verified `sub` becomes the stable application and Composio user ID.
7. User-scoped CRUD and retrieval use the user token so RLS remains effective.

Supabase recommends verified claims/JWKS rather than trusting locally decoded session data. See [Supabase JWT verification](https://supabase.com/docs/guides/auth/jwts).

Security rules:

- RLS on every exposed table.
- Revoke default grants, then grant only required operations.
- Explicit ownership or workspace-membership predicates.
- Separate policies for select, insert, update, and delete.
- Both `USING` and `WITH CHECK` for updates.
- `security_invoker` views and functions wherever possible.
- Service/secret key only in backend workers and migration jobs.
- Storage policies tied to the workspace path.
- pgTAP allow-and-deny tests for every table and bucket.
- Zero cross-tenant leakage is a release-blocking invariant.

Supabase recommends testing RLS policies with `supabase test db`, not merely checking that policies exist. See the [Supabase RLS guide](https://supabase.com/docs/guides/database/postgres/row-level-security).

## 6. Composio tool architecture

Use the current `composio` package and stable Composio Sessions with `composio_langchain`. Do not use the legacy `composio-core` SDK or old experimental Tool Router API. Composio’s LangChain provider produces tools for current LangChain and LangGraph agents. See the [Composio LangChain provider](https://docs.composio.dev/docs/providers/langchain) and [Composio Sessions](https://docs.composio.dev/docs/how-composio-works).

For every authenticated user:

- Create or reuse a Composio session using the Supabase user UUID.
- Store only Composio session/account identifiers locally.
- Let Composio store and refresh provider OAuth tokens.
- Verify callback identity before activating a connection.
- Support explicit aliases such as `work` and `personal`.
- Never rely on an implicit account when multiple accounts exist.

Initial tool policy:

| Capability | Initial policy |
|---|---|
| Web search | Read-only, automatic |
| Calendar list/search | Read-only, automatic |
| Calendar create/update | Human approval |
| Calendar delete | Human approval plus explicit confirmation |
| Email read/search | Read-only, opt-in |
| Email draft | Approval optional |
| Email send | Always approval |
| Storage/Drive read | Scoped read-only |
| Any destructive tool | Denied unless explicitly enabled |
| Remote shell/workbench | Disabled |

Composio supports toolkit/tool allowlists, read-only/destructive tags, account pinning, and disabling its sandbox. Use narrow allowlists and enforce an additional local policy because metadata tags are not a substitute for authorization. See [Configuring Composio Sessions](https://docs.composio.dev/docs/configuring-sessions).

LangGraph interrupts persist the graph before approval and allow approve, edit, or reject decisions. See [LangGraph human-in-the-loop](https://docs.langchain.com/oss/python/langchain/human-in-the-loop).

## 7. Agent harness engineering

The harness should control the model, not merely prompt it.

The request classifier first chooses the deterministic RAG graph or the bounded research/tool graph. The agent loop is an explicit state machine:

```text
classify → plan next bounded action → policy check
              ├── retrieve/read-only tool → observe → update evidence
              ├── side effect → persist approval interrupt
              ├── enough evidence → synthesize → verify → finish
              └── budget/deadline reached → partial answer or abstain
```

The model may propose actions, but deterministic code validates authorization, tool allowlists, connection ownership, argument schemas, approval policy, idempotency, and budgets before execution. Tool output returns as untrusted, size-bounded evidence with provenance. The graph never copies tool or retrieved text into system instructions.

Each tool receives metadata defining:

- Risk level.
- Read/write/destructive classification.
- Required scopes.
- Timeout.
- Retry policy.
- Idempotency behavior.
- Approval requirement.
- Maximum result size.
- Redaction policy.

Middleware controls:

- Model and tool-call limits.
- Retry only for classified transient errors.
- Model fallback.
- PII redaction in traces and tool results.
- Context trimming and conversation summarization.
- Prompt-injection detection.
- Tool-output size limits.
- Cost budgets.
- Final structured-response validation.

The graph state records termination reason, remaining budgets, evidence lineage, attempted strategies, tool results by reference, and pending approval state. A run has a configurable deadline and hard ceilings for graph steps, model calls, retrieval passes, tool calls, tool-result bytes, input/output tokens, and estimated spend. The verifier may request at most one bounded repair; it cannot start an unrestricted reflection cycle.

Write-tool execution uses a durable intent record and idempotency key. After approval, resume logic revalidates the user, membership, connection, scopes, arguments, expiry, and policy before the side effect. Approval is not transferable between materially different arguments. Timeouts or ambiguous provider responses enter a reconciliation state rather than blindly retrying the write.

Prompt injection remains possible even with RAG. OWASP recommends minimum tool functionality, minimum permissions, execution in the user’s own identity, and human approval for high-impact actions. See [OWASP Prompt Injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/) and [OWASP Excessive Agency](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/).

## 8. Provider and runtime abstractions

Portability is deliberate but must not create lowest-common-denominator code. Each profile declares capabilities; routing rejects an incompatible model before a run starts.

### Model profiles

`ModelProfile` records provider, model, purpose, temperature, token limits, timeout, retry/fallback policy, cost and latency class, data-retention eligibility, region restrictions, and capability flags such as structured output, tool calling, vision, reasoning, long context, and streaming. Business logic asks for a purpose/capability profile, not a vendor model string.

The first release implements Groq as the only required chat/reasoning provider through `langchain-groq` and `ChatGroq`. The initial configuration candidates are:

| Alias | Initial Groq model candidate | Purpose |
|---|---|---|
| `fast_structured` | `openai/gpt-oss-20b` | Query classification, routing, evidence grading, extraction |
| `quality` | `openai/gpt-oss-120b` | Grounded answer synthesis and difficult reasoning |
| `agent` | `openai/gpt-oss-120b` | Bounded LangGraph planning and local Composio tool calls |

These are benchmark defaults, not permanent database constants. Deployment configuration maps aliases to model IDs, and startup/readiness probes verify that each configured model exists, is permitted for the Groq project, and supports the required capability. Model changes require evaluation rather than code changes. Groq currently labels GPT-OSS 120B as a production model and exposes active models through its Models API. See [Groq models](https://console.groq.com/docs/models) and [model permissions](https://console.groq.com/docs/model-permissions).

Groq strict structured output is used for non-streaming classification, grading, and extraction calls where supported. Groq currently does not combine Structured Outputs with streaming or tool use, so answer streaming and agent tool calls use separate profiles plus Pydantic validation and at most one bounded repair. Do not silently downgrade a strict call to unvalidated JSON. See [Groq Structured Outputs](https://console.groq.com/docs/structured-outputs).

Groq is initially an inference provider only. Composio and locally defined LangGraph tools remain behind our policy, approval, audit, and budget layers; Groq Compound, built-in browser tools, and remote MCP execution are disabled initially so they cannot bypass those controls. They may be evaluated later as separate strategies.

Rate limits apply at the Groq organization level. The adapter observes `retry-after` and Groq rate-limit headers, uses bounded concurrency and jittered transient retries, and emits per-profile usage/latency metrics without exposing the API key. See [Groq rate limits](https://console.groq.com/docs/rate-limits).

Production must explicitly review Groq Data Controls. Inference data is not retained by default except for limited reliability/abuse cases, Zero Data Retention can be enabled, and retained customer data is located in the United States. Those facts must be reconciled with workspace residency and compliance requirements before production. See [Your Data in GroqCloud](https://console.groq.com/docs/your-data).

The provider port remains because model lifecycle and enterprise requirements change. A non-Groq fallback is not implemented until an evaluation and privacy review justify it; if later added, fallback must preserve residency, retention, feature, safety, and budget policy rather than routing blindly across vendors.

### Embedding profiles

The embedding port exposes bounded batch embedding plus model metadata. Persistence records provider, model, version, dimension, normalization, and pipeline version. Upgrades build and evaluate a parallel index before an atomic knowledge-base profile switch. Query embeddings and stored vectors must have the same active profile.

### Reranker profiles

The reranker port accepts a typed query and authorized candidate set and returns stable candidate identifiers with scores. Cross-encoder, API, LLM-based, and no-reranker baselines remain independently benchmarkable. Candidate counts, document text sent off-platform, timeouts, and fallback behavior are policy-controlled.

### Redis cache and coordination policy

Candidate caches include query normalization, embeddings for non-sensitive normalized text, retrieval candidates, reranker output, web-search results, tool schemas, rate-limit counters, and short-lived provider metadata. Caching is opt-in per data class.

- Never cache authorization decisions, raw credentials, access tokens, approval decisions, or mutable security policy.
- Keys include tenant/workspace, knowledge base, authorization fingerprint where required, document/index versions, retrieval configuration, model profile, and schema version.
- Values have TTLs, size limits, encryption/transport requirements, and explicit invalidation triggers.
- A cache miss or cache loss changes performance, never correctness or durable state.
- Distributed locks have ownership tokens and finite leases; correctness cannot depend on a lock surviving Redis loss.

## 9. API contract

Initial endpoints:

```text
GET    /health/live
GET    /health/ready

GET    /v1/me
GET    /v1/workspaces
POST   /v1/knowledge-bases
GET    /v1/knowledge-bases/{id}

POST   /v1/documents/uploads
POST   /v1/documents/{id}/ingest
GET    /v1/documents/{id}
GET    /v1/ingestion-jobs/{id}
POST   /v1/ingestion-jobs/{id}/cancel
POST   /v1/ingestion-jobs/{id}/retry
DELETE /v1/documents/{id}

POST   /v1/conversations
GET    /v1/conversations/{id}
POST   /v1/conversations/{id}/messages
GET    /v1/conversations/{id}/events

GET    /v1/connections
POST   /v1/connections/{toolkit}/authorize
DELETE /v1/connections/{id}

GET    /v1/approvals/{id}
POST   /v1/approvals/{id}/approve
POST   /v1/approvals/{id}/reject

POST   /v1/feedback
```

Mutating endpoints accept an idempotency key where replay is plausible. Job creation returns `202 Accepted` with the authoritative job URL. Cancellation returns the requested state and does not claim that a running external operation stopped instantly. SSE events have stable event IDs and typed payloads so a client can reconnect; durable messages and approvals remain queryable even when the stream disconnects.

Errors use a versioned envelope with safe public codes, request/trace identifiers, retryability, and field-level details where appropriate. Internal exception messages and provider payloads are not returned to clients.

Answers should use a structured schema resembling:

```json
{
  "answer": "...",
  "citations": [
    {
      "source_id": "...",
      "document_id": "...",
      "version_id": "...",
      "page": 12,
      "section": "Security",
      "quote": "...",
      "score": 0.93
    }
  ],
  "retrieval_mode": "hybrid_reranked",
  "confidence": "high",
  "warnings": [],
  "pending_approval": null
}
```

## 10. Repository structure

A `uv` workspace keeps API, worker, and shared components separate while using one lockfile:

```text
.
├── apps/
│   ├── api/
│   │   └── src/rag_api/
│   └── worker/
│       └── src/rag_worker/
│           ├── consumers/
│           ├── tasks/
│           └── infrastructure/
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
│           ├── tools/
│           ├── models/
│           ├── embeddings/
│           ├── policies/
│           └── observability/
├── infrastructure/
│   ├── docker/
│   └── redis/
├── supabase/
│   ├── migrations/
│   ├── seed.sql
│   └── tests/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── security/
│   ├── contract/
│   └── failure/
├── evals/
│   ├── datasets/
│   ├── evaluators/
│   ├── baselines/
│   └── experiments/
├── docs/
│   ├── architecture/
│   ├── adr/
│   └── runbooks/
├── pyproject.toml
├── uv.lock
├── docker-compose.yml
└── README.md
```

This structure is directional: preserve feature cohesion and avoid empty directory ceremony. No legacy runtime package is carried into the new workspace.

## 11. Reliability and observability

### Cross-system context

Propagate W3C trace context plus applicable `request_id`, `job_id`, `conversation_id`, `workspace_id`, `document_id`, and `document_version_id` through API, outbox, broker, worker, retrieval, model, and tool calls. Identifiers may appear in access-controlled structured logs and traces, but high-cardinality or tenant identifiers must not become unrestricted metric labels.

Minimum telemetry:

| Surface | Signals |
|---|---|
| API | request latency, time to first token, total stream duration, status, disconnects, payload class |
| Outbox/queue | undispatched age/count, enqueue rate/failure, queue depth, oldest job age, retries, dead letters, concurrency |
| Ingestion | per-stage duration, pages/chunks, embedding batches/tokens, artifact sizes, failed stage, lease recovery, total duration |
| Retrieval | dense/lexical latency, candidate counts, RRF channel contribution, reranker latency, selected chunks/tokens, strategy/escalation |
| Model | profile, latency/TTFT, tokens, estimated cost, retry/fallback count, termination reason |
| Agent/tools | graph steps, tool calls/failures, approvals, trajectory length, budget use, ambiguous side effects |

Use structured JSON logs, OpenTelemetry-compatible traces/metrics, and redaction at collection time. LangSmith may provide LangGraph/model traces and evaluation, but domain telemetry, audit logs, and incident diagnosis must remain usable without it. Sample successful high-volume traces; retain errors and security/audit events under explicit policy. Never log access tokens, raw OTPs, provider credentials, unrestricted document text, or full sensitive tool responses.

### Error taxonomy and retry policy

Use typed internal errors mapped to stable API/job codes. Initial families include authentication, authorization, invalid upload, unsupported or malicious document, storage, queue/dispatch, lease/worker timeout, parse, chunk, embedding, index, retrieval, reranker, insufficient evidence, model provider, tool, tool permission, approval, budget, and deadline failures.

Every external operation declares timeout, maximum attempts, exponential backoff with jitter, retryable error classes, idempotency characteristics, and a total deadline. Permanent validation/auth errors do not retry. Rate limits and transient network/server failures may retry within budget. Destructive or side-effecting tool calls do not automatically retry without a provider-supported or application-enforced idempotency/reconciliation contract.

### Failure and recovery invariants

- API success cannot be required for a committed job to remain discoverable.
- Redis/cache loss cannot remove durable intent or mark incomplete content active.
- A dead worker lease eventually becomes runnable or terminal through reconciliation.
- Repeated delivery cannot create duplicate chunks, active versions, tool side effects, or audit gaps.
- A partial ingestion is invisible to normal retrieval.
- A disconnected client can recover authoritative answer, job, tool-run, and approval state.
- Recovery procedures are exercised by automated failure tests and documented runbooks.

## 12. Evaluation strategy

Evaluation must exist before advanced retrieval tuning.

Dataset categories:

- Exact product codes and error identifiers.
- Semantic paraphrases.
- Table and scanned-PDF questions.
- Multi-document and multi-hop questions.
- Whole-corpus aggregation.
- Conflicting or outdated documents.
- Unanswerable questions.
- Freshness-dependent questions requiring web search.
- Prompt injection embedded in uploaded documents or web pages.
- Cross-tenant access attempts.
- Correct and incorrect tool-choice scenarios.
- Approval and cancellation scenarios.
- Duplicate delivery, lost broker state, expired leases, and outbox replay.
- Cache hit/miss equivalence and authorization-fingerprint invalidation.

Metrics:

- Retrieval: Recall@k, Precision@k, MRR, nDCG, fused-channel contribution.
- Generation: correctness, groundedness, completeness, relevance.
- Citations: precision, recall, source-span validity, document-version validity.
- Abstention: correct refusal on insufficient evidence.
- Agent: correct tool, correct arguments, correct trajectory, unnecessary calls.
- Safety: unauthorized reads/writes and unapproved side effects.
- Operations: ingestion success, duplicate suppression, stale index rate.
- Resilience: outbox age, lease recovery time, replay success, eventual terminal-state rate.
- Performance: time to first token, total p50/p95 latency, tokens and cost.
- Human feedback and pairwise preference.

LangSmith supports offline regression datasets and online production evaluators for correctness, groundedness, relevance, retrieval relevance, tool trajectories, latency, and cost. See [LangSmith RAG evaluation](https://docs.langchain.com/langsmith/evaluate-rag-tutorial) and [offline and online evaluation](https://docs.langchain.com/langsmith/evaluation).

Provisional release gates:

- Zero cross-tenant leakage.
- Zero side effects without required approval.
- Retrieval Recall@20 of at least 90% on the initial gold dataset.
- Citation precision and groundedness of at least 95%.
- At least 90% correct abstention on unanswerable cases.
- No quality regression beyond an agreed tolerance.
- Latency and cost budgets defined separately for standard RAG and agentic runs.
- All committed jobs recover after simulated worker and Redis loss without duplicate active versions.
- Cached and uncached execution produce equivalent authorized evidence and answers within defined nondeterminism tolerance.

## 13. CI/CD and deployment

### Pull-request workflow

- `uv lock --check`
- `uv sync --locked --all-extras --dev`
- Ruff formatting and linting.
- Static type checking.
- Unit and contract tests.
- Local Supabase migration reset.
- pgTAP RLS/storage policy tests.
- Integration tests against local Postgres/pgvector.
- Redis/Dramatiq adapter tests and worker-process integration tests.
- Transactional-outbox, duplicate-delivery, lease-expiry, cancellation, and Redis-loss recovery tests.
- API OpenAPI-schema snapshot.
- Fast smoke-evaluation suite.
- Dependency audit and SBOM generation.
- Secret scanning and CodeQL.
- Actions pinned to full commit SHAs.

GitHub says full-length commit SHAs are the only immutable way to pin third-party actions. See [GitHub Actions secure use](https://docs.github.com/en/actions/reference/security/secure-use).

### Deployment workflow

- Separate staging and production Supabase projects.
- Separate staging and production Redis resources and credentials; broker persistence/HA configuration is reviewed as infrastructure.
- Expand-compatible migrations before application rollout.
- Automatic staging deployment after `main` passes.
- Staging smoke tests and evaluation sample.
- Protected production environment with approval and deployment concurrency.
- FastAPI Cloud deploy token stored only as a production environment secret.
- Scheduled deploy-token rotation.
- Health verification after deployment.

FastAPI Cloud provides deploy tokens and GitHub Actions setup, along with gradual zero-downtime deployment. See [FastAPI Cloud CI setup](https://fastapicloud.com/docs/fastapi-cloud-cli/setup-ci/) and [deployment behavior](https://fastapicloud.com/docs/builds-and-deployments/how-it-works/).

### Important deployment boundary

FastAPI Cloud should host the request-serving API. Heavy Docling/OCR/embedding work needs a dedicated worker runtime.

FastAPI explicitly warns against using in-process `BackgroundTasks` for heavy computation, and FastAPI Cloud is request-autoscaled with modest default memory. See the [FastAPI background-task caveat](https://fastapi.tiangolo.com/tutorial/background-tasks/) and [FastAPI Cloud resources](https://fastapicloud.com/pricing/).

Recommended worker options:

1. A separately hosted CPU/GPU Dramatiq worker consuming the production Redis broker.
2. A managed `docling-serve` deployment plus a lightweight Dramatiq worker for orchestration and indexing.
3. A second always-on FastAPI Cloud application only if background process lifecycle, worker concurrency, timeouts, and resource support are validated during a deployment spike.

The worker interface remains portable so the API is not coupled to a particular compute provider.

### Local and low-cost development

Use Docker Compose for the API, a non-public Redis instance, and Dramatiq worker; use the Supabase local development stack for Postgres/pgvector, Auth, Storage, migrations, and RLS testing where practical. Docling runs locally or behind a local `docling-serve`. No paid service is required for routine development and CI, but local defaults must not be mistaken for production durability settings.

## 14. Required architecture decision records

Milestone 0 creates concise ADRs for:

1. Deterministic RAG versus bounded agent execution.
2. Supabase as the primary persistent data platform.
3. Redis plus Dramatiq for initial background execution, including why PGMQ was not selected and the conditions for revisiting the decision.
4. Queue port, transactional outbox, and infrastructure portability.
5. PostgreSQL `ingestion_jobs` as authoritative job state.
6. Hybrid dense/lexical/RRF/reranked retrieval as the baseline.
7. Evaluation-gated adaptive and advanced retrieval.
8. Model, embedding, reranker, and retrieval-strategy profiles.
9. Embedding/index versioning and activation.
10. Human approval and idempotency policy for side-effecting tools.
11. API/worker/LangGraph responsibility and deployment separation.
12. LangGraph checkpoint persistence, security, and retention.

## 15. Deliberately deferred work

Do not build Kafka, RabbitMQ, Temporal, Kubernetes, custom distributed scheduling, complex autoscaling, GPU infrastructure, GraphRAG, RAPTOR, ColBERT, multiple production model providers, or multiple simultaneous embedding indexes during the foundation milestones. Define only the narrow ports and version fields required to keep later experiments possible. Promote any of these only when a measured workload or evaluation justifies its cost and an ADR records the decision.

## 16. Open decisions and validation spikes

These decisions remain open because choosing them without measurements would create false precision:

- Production worker host, CPU/memory/GPU sizing, regional placement, autoscaling floor, and shutdown behavior.
- Production Redis topology, vendor, persistence/HA tier, broker/cache isolation, recovery-point objective, and recovery-time objective.
- Final Groq model-to-profile mapping and whether a non-Groq disaster fallback is justified.
- Embedding provider/model/dimension, reranker, and web-search provider; Groq selection does not decide embeddings.
- Groq Zero Data Retention, US data-location acceptability, project/model permissions, and production rate-limit tier.
- Malware-scanning service and accepted file/size/decompression policies.
- LangGraph checkpoint schema/package compatibility, retention, encryption/redaction, and pruning.
- SMTP provider, OTP versus magic-link presentation, email deliverability, and account-recovery UX.
- Data residency, retention, deletion, backup, and compliance requirements.
- Concrete latency, quality, cost, and ingestion-throughput service-level objectives after the initial corpus benchmark.

Milestone 0 resolves or explicitly defers each item with an owner, evidence, and due milestone.

## Implementation milestones

### Milestone 0 — Architecture and evaluation foundation

- Treat this merged document as canonical and retain the amendment as history.
- Write the required architecture decision records.
- Define queue envelopes, job/outbox records, leases, state transitions, retry classes, cancellation, and reconciliation contracts.
- Define model, embedding, reranker, retrieval-strategy, tool-policy, and response contracts.
- Benchmark the candidate Groq model profiles for routing, grading, synthesis, streaming, and sequential tool use; record quality, schema validity, latency, token use, and 429 behavior.
- Build the first 100–200 question gold dataset plus security, abstention, tool, and recovery cases.
- Establish the simple hybrid/no-reranker baseline before comparing chunking, embedding, and reranker candidates.
- Spike FastAPI Cloud API limits, worker hosting, Redis/Dramatiq failure recovery, LangGraph Postgres checkpoints, and end-to-end trace propagation.
- Propose measurable latency, quality, ingestion throughput, safety, and cost budgets.

Exit gate: ADRs and contracts are reviewable; baseline evaluation runs reproducibly; all open production-provider decisions have an owner and validation path.

### Milestone 1 — Project foundation

- Create the Python 3.12 `uv` workspace with only the new application packages.
- Add FastAPI and Dramatiq worker application skeletons.
- Add the Groq `ChatGroq` adapter, model-profile configuration, fake/test implementation, startup capability checks, concurrency limits, and a provider smoke test.
- Add typed settings, structured/redacted logging, trace context, health/readiness, and graceful lifecycle handling.
- Add Docker Compose for local Redis and application processes, with explicit broker/cache configuration.
- Add the `JobQueue` port, Redis/Dramatiq adapter, job envelope, actor registry, and test broker.
- Create Supabase local configuration and initial migrations for durable job/outbox primitives needed by the foundation.
- Add the outbox dispatcher/reconciler skeleton and cooperative cancellation contract.
- Add GitHub Actions for lock, lint, types, tests, migrations/security checks, secret scanning, and a small smoke evaluation.
- Document setup, architecture boundaries, local operation, and failure recovery.

Exit gate: a typed demo job can be committed, dispatched, processed, observed, cancelled cooperatively, deduplicated, and recovered after simulated Redis/worker loss. Do not build the full RAG pipeline yet.

### Milestone 2 — Identity and data isolation

- OTP login contract.
- JWT verification.
- Workspaces and memberships.
- RLS, grants, Storage policies, and pgTAP tests.
- Separate browser, API, worker, and migration credentials.

### Milestone 3 — Durable ingestion

- Signed/resumable uploads.
- Redis/Dramatiq dispatch through the queue port and transactional outbox.
- Job state/stage machine, leases, heartbeats, cooperative cancellation, reconciliation, and dead-letter handling.
- Docling parser and normalized artifacts.
- Versioned, structure-aware chunking.
- Embedding and index lifecycle.
- Retry classification, deletion, repair, and reindex paths.
- Stage metrics, traces, safe errors, and failure-injection tests.

### Milestone 4 — Production RAG

- Dense and full-text retrieval.
- RRF, reranking, metadata filters, neighbor expansion.
- Citation construction and verification.
- Evidence grading and abstention.
- Streaming Q&A API.
- Retrieval and answer evaluations.

### Milestone 5 — Agent and tools

- Typed LangGraph state.
- Composio Sessions and connection UI contract.
- Read-only web and calendar tools.
- Approval interrupts for writes.
- Budgets, middleware, audit log, and error taxonomy.
- Tool-selection and trajectory evaluations.

### Milestone 6 — Advanced retrieval experiments

- Contextual embeddings/BM25.
- Multi-query and decomposition.
- RAPTOR for selected long-document collections.
- GraphRAG for selected global-analysis collections.
- Late interaction only if benchmark results justify its added infrastructure.

### Milestone 7 — Production hardening

- Load, failure-recovery, outbox, Redis-loss, and queue tests.
- Prompt-injection and tenant-boundary red team.
- LangSmith/OpenTelemetry with redaction and sampling.
- Backups, recovery, retention, key rotation, and runbooks.
- Staging and protected production deployments.

## Recommended starting point

When implementation is authorized, begin with Milestone 0, then Milestone 1. Establish the contracts and measurable baseline, create the clean `uv` workspace, and prove the API/job/worker and Groq-provider skeletons before writing the actual RAG graph.

### Milestones 0–1 implementation checklist

- [ ] Approve the canonical architecture and unresolved-decision owners.
- [x] Add ADR-001 through ADR-012.
- [x] Specify typed domain contracts and state-transition invariants.
- [ ] Seed versioned evaluation and adversarial/recovery datasets.
- [ ] Record simple retrieval and ingestion-spike baselines.
- [ ] Benchmark and select the initial Groq `fast_structured`, `quality`, and `agent` model mappings.
- [ ] Decide Groq Data Controls/ZDR, model permissions, budgets, and rate-limit assumptions.
- [ ] Confirm API and worker deployment boundaries with a runnable spike.
- [x] Scaffold the `uv` workspace, API, worker, core package, tests, evals, infrastructure, and Supabase directories.
- [x] Add Docker Compose Redis and local Supabase workflows.
- [ ] Implement settings, structured logging/tracing, health, and readiness.
- [ ] Implement the `ChatGroq` provider adapter, fake provider, capability checks, usage telemetry, and rate-limit handling.
- [ ] Implement the queue port, Dramatiq/Redis adapter, outbox dispatcher, reconciler, leases, and cooperative cancellation skeleton.
- [ ] Prove duplicate delivery, Redis loss, worker death, retry exhaustion, and cancellation behavior in tests.
- [ ] Add locked CI, migration/RLS checks, security scanning, and smoke evaluation.
- [ ] Document local setup, secrets, recovery, and the handoff into Milestone 2.

### Implementation start sequence

The first implementation should be delivered as small, independently reviewable slices:

1. **Architecture contracts:** ADRs, typed job/model/retrieval contracts, state-transition table, settings names, and test strategy.
2. **Workspace scaffold:** root `pyproject.toml`, `uv.lock`, API/worker/core packages, test layout, configuration loading, logging, and health/readiness.
3. **Local infrastructure:** Supabase local configuration, initial job/outbox migrations, Redis Docker configuration, and developer commands.
4. **Reliable job vertical slice:** create one demo job and outbox event, dispatch it through Redis/Dramatiq, update authoritative state, and prove replay, duplicate suppression, cancellation, and worker-death recovery.
5. **Groq vertical slice:** invoke `ChatGroq` through a provider port, run one strict structured classification and one streamed response, capture tokens/latency/request IDs, and test 429, timeout, invalid model, malformed output, and missing-key behavior.
6. **CI and handoff:** locked dependency checks, lint/types/tests, Supabase reset, failure tests, provider contract tests with mocked defaults and an opt-in live Groq smoke test, plus local runbooks.

The first usable demonstration is therefore not a full chatbot: it is a healthy FastAPI service that can submit/recover background work and execute observable, typed Groq calls through stable interfaces. That foundation is the entry gate for authentication and the real ingestion/RAG pipeline.
