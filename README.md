# Adaptive & Corrective Agentic RAG

A distributed retrieval-augmented generation engine implementing bounded state graphs, hybrid search (HNSW pgvector + BM25 tsvector), cross-encoder reranking, transactional outbox ingestion, and deterministic citation verification.

---

## 1. Architectural Thesis: Beyond Naive RAG

Most retrieval-augmented generation systems are constructed as linear scripts: an unindexed prompt template chained to a single vector database query and an unbounded language model call. 

While sufficient for static single-document demos, naive pipelines fail predictably under real-world workloads:
- **Conversational Pronoun Starvation**: When a user follows up with *"What did it cost?"*, a naive vector search queries the pronoun *"it"*, retrieving completely irrelevant chunks.
- **Semantic Distance Blind Spots**: High-dimensional vector cosine distance excels at semantic similarity but frequently fails on exact keyword identifiers (part numbers, legal clause codes, error hashes).
- **The "Lost-in-the-Middle" Position Decay**: Bi-encoder vector search returns chunks based on individual embedding distances. Stuffed into a large context window, language models focus disproportionately on the first and last tokens, ignoring critical evidence buried in the middle chunks.
- **Information Starvation**: If the local index contains zero relevant context, a naive pipeline forces the generator to answer anyway, triggering hallucinations.
- **Distributed Dual-Write Inconsistency**: Ingestion scripts that upload a file and immediately call a remote vector database risk partial failures—if the vector database network call drops, the database and vector store drift out of sync permanently.

This platform replaces ad-hoc chains with canonical retrieval architectures—combining **Adaptive RAG** (evaluating query complexity to route execution), **Corrective RAG / CRAG** (evaluating evidence sufficiency with automated fallback), **Dual-Engine Hybrid Search with Reciprocal Rank Fusion**, **Local ONNX Cross-Encoder Reranking**, and **ACID Transactional Outbox Ingestion**.

### Architectural Comparison: Naive Pipeline vs. Bounded Agentic RAG

| Architectural Dimension | Naive / Tutorial RAG | Bounded Agentic Architecture (This System) |
| :--- | :--- | :--- |
| **Control Flow** | Hardcoded linear pipe: `Query -> Embed -> Retrieve -> LLM`. Cannot branch, retry, or self-correct. | **Deterministic StateGraph**: Dynamically routes between direct answers, local hybrid retrieval, and web search fallback. |
| **Conversational Memory** | Stuffs raw chat history into vector search or prompt, corrupting embedding similarity. | **Query Condensation**: Sub-second LPU inference rewrites pronouns and multi-turn context into self-contained search queries. |
| **Retrieval Engine** | Single dense vector index (approximate nearest neighbor only). | **Dual-Engine Hybrid**: Dense cosine HNSW + BM25 `tsvector` GIN fused via PostgreSQL Reciprocal Rank Fusion ($k=60$). |
| **Candidate Rescoring** | None. LLM receives top-$k$ purely ordered by bi-encoder cosine distance. | **Local ONNX Cross-Encoder**: Joint self-attention over query-passage pairs eliminates position bias and filters noise. |
| **Zero-Evidence Handling** | LLM hallucinates or produces ungrounded guesses when retrieval is empty. | **Autonomous Fallback**: Corrective router detects zero-chunk states and routes to external web search tools. |
| **Ingestion Consistency** | Dual-write hazard: file store and vector store updated in separate, uncoordinated network calls. | **Transactional Outbox**: Document metadata, staging, and outbox events committed in a single ACID PostgreSQL transaction. |
| **Queue Concurrency** | Unmanaged background threads or memory queues prone to data loss on worker crash. | **`FOR UPDATE SKIP LOCKED` Polling**: Transactional dispatcher feeds Redis 8 and Dramatiq with distributed ack/retry semantics. |
| **Citation Verification** | Generator is trusted to output accurate bracketed citations. | **AST Citation Audit**: Verbatim passage inspection validates bracketed references against retrieved chunk UUIDs. |

---

## 2. System Topology & Component Interactions

<p align="center">
  <img src="docs/diagrams/system_topology.svg" alt="RAG-Agent System Topology" width="100%">
  <br>
  <em>Multi-tier architectural topology, network boundaries, and component interactions.</em> &bull;
  <a href="docs/diagrams/system_topology.html"><strong>Open Interactive Diagram Viewer ↗</strong></a>
</p>

---

## 3. Technology Stack & Specifications Matrix

The platform integrates 15 core technologies organized across discrete architectural tiers. Every technology is selected according to explicit algorithmic characteristics, hardware acceleration models, or consistency guarantees:

| Architectural Tier | Technology | Specification / Version | Architectural Role | Concrete Technical Justification & Invariants |
| :--- | :--- | :--- | :--- | :--- |
| **Reasoning & State Graph** | **LangGraph** | `~=1.2.12` | Bounded cyclic state machine orchestration | Enforces strict acyclic state bounds with $O(1)$ maximum transition steps per turn. Prevents unbounded recursive loops common in unconstrained autonomous agents. Supports in-memory (`MemorySaver`) and durable (`SqliteSaver`, `PostgresSaver`) checkpointing. |
| **Inference Hardware** | **Groq LPU** | `Llama-3.1-8B-Instant` & `Llama-3.3-70B-Versatile` | Dual-tier LLM inference execution | Language Processing Units (LPUs) provide deterministic execution speeds (300–800 tokens/sec). `8B-Instant` handles sub-second query condensation and routing (<150ms). `70B-Versatile` performs grounded context synthesis and AST-validated citation formatting. |
| **Dense Vector Embeddings** | **FastEmbed** | `BAAI/bge-small-en-v1.5` (`384-dim`) | Local dense embedding generation | Runs directly in-process via ONNX Runtime on CPU. Eliminates external embedding API costs, network round-trip overhead, and remote dual-write vulnerabilities during ingestion. Normalized vectors guarantee cosine distance compatibility. |
| **Passage Reranking** | **FlashRank** | `ms-marco-TinyBERT-L-2-v2` | Cross-encoder semantic rescoring | Runs locally on CPU via ONNX Runtime (<20ms latency). Evaluates full token-level cross-attention over query-passage pairs ($[\text{CLS}] \circ q \circ [\text{SEP}] \circ d$), overcoming bi-encoder lost-in-the-middle attention decay. |
| **Vector Storage & Search** | **PostgreSQL 16 + pgvector** | `pgvector 0.3+` (HNSW) | Approximate nearest neighbor vector store | Hierarchical Navigable Small World (HNSW) index using cosine distance (`vector_cosine_ops`) with $m=16$, $ef_{\text{construction}}=64$. Delivers logarithmic $O(\log N)$ search complexity without external vector database drift. |
| **Lexical Full-Text Search** | **PostgreSQL GIN tsvector** | `english` regconfig | Sparse BM25-style keyword retrieval | Stored generated `tsv_content` column indexed via Generalized Inverted Index (GIN). Guarantees exact keyword matching for alphanumeric identifiers, code hashes, and domain acronyms missed by dense vector embeddings. |
| **Hybrid Rank Fusion** | **PostgreSQL RRF RPC** | `match_chunks_hybrid(k=60)` | In-database reciprocal rank fusion | Executes fusion inside the database engine, avoiding client-side candidate fetching. Merges dense vector and sparse lexical ranks using smoothing parameter $k=60$: $\text{RRF}(d) = \sum (60 + r_m(d))^{-1}$. |
| **Reliability Pattern** | **Transactional Outbox Table** | `private.job_dispatch_outbox` | ACID event staging queue | Ingestion endpoint writes document metadata, version staging, and outbox dispatch records inside a single atomic PostgreSQL transaction. Guarantees zero orphaned uploads or dual-write inconsistency during network failures. |
| **Queue Message Broker** | **Redis 8 Alpine** | `redis:8.2.9-alpine` (AOF) | Asynchronous task transport channel | Decouples HTTP request ingestion from heavy CPU vector embedding. Configured with Append-Only File (AOF) persistence for crash recovery and bounded queue latency. |
| **Background Ingestion** | **Dramatiq Worker Pool** | `dramatiq[redis] ~=2.2` | Distributed document parsing and vectorization | Multi-threaded worker pool consuming from Redis. Executes format extraction (PDF, Markdown, plaintext), semantic chunking (500 tokens / 50 overlap), FastEmbed vector computation, and batch PostgreSQL inserts. |
| **API Gateway & Streaming** | **FastAPI** | `>=0.141, <1.0` (ASGI) | HTTP interface & Server-Sent Events (SSE) | Asynchronous non-blocking web framework providing `/v1/agent/stream` and `/v1/chat/stream` SSE endpoints, multipart document ingest, and non-blocking socket readiness probes (`/health/ready`). |
| **External Knowledge Fallback** | **DuckDuckGo / Tavily** | `WebSearchPort` provider | Corrective web search fallback (CRAG) | Activates dynamically when local hybrid retrieval returns zero chunks ($|\text{chunks}| = 0$). Supplies real-time external web context to prevent model hallucination on out-of-index domains. |
| **Authentication & Multi-Tenancy** | **Supabase / PyJWT Auth** | `HS256` / `RS256` Verifier | Multi-tenant token verification & RLS | Cryptographically validates incoming JWT tokens against workspace UUID claims before granting query access. Aligns with PostgreSQL Row-Level Security (RLS) policies isolating workspace records. |
| **Package & Workspace Runtime** | **Astral uv** | `uv >=0.10.3` | Deterministic monorepo package management | Resolves and freezes workspace dependencies across `rag-api`, `rag-worker`, and `rag-core` in a single `uv.lock`. Delivers sub-second dependency resolution and reproducible isolated environments. |
| **Quality & Security Tooling** | **Tooling Suite** | MyPy, Ruff, Pytest, Gitleaks | Static typing, linting, testing, and secret scanning | Enforces strict typing (`disallow_untyped_defs = true`, `strict_equality = true`), deterministic formatting via Ruff, 81 automated contract and unit tests via Pytest, and automated secret prevention via Gitleaks. |

---

## 4. Core Architectural Pillars

### 4.1 Bounded StateGraph & Query Condensation (`AdaptiveRagGraph`)
The reasoning engine is structured as a bounded LangGraph `StateGraph`. Unlike autonomous loop agents that can diverge into unbounded recursion, this graph enforces a finite state machine:

<p align="center">
  <img src="docs/diagrams/agent_stategraph.svg" alt="Bounded Agent StateGraph Transitions" width="100%">
  <br>
  <em>Bounded LangGraph StateGraph transitions, routing conditionals, and evidence evaluation.</em> &bull;
  <a href="docs/diagrams/agent_stategraph.html"><strong>Open Interactive Diagram Viewer ↗</strong></a>
</p>

- **Query Condensation**: Multi-turn conversations frequently introduce pronouns (*"What are its limits?"*, *"Can you elaborate on that point?"*). Before querying the database, the agent calls a high-speed LPU model (`llama-3.1-8b-instant`) to rewrite the conversation into an independent, disambiguated query string.
- **Corrective Fallback**: If candidate retrieval yields zero chunks—indicating an out-of-domain query or an empty workspace index—the agent automatically activates the `web_search_fallback` node to fetch external real-time context rather than returning an empty hallucination.

### 4.2 Dual-Engine Hybrid Retrieval & Reciprocal Rank Fusion
Vector similarity alone misses exact identifiers, while lexical full-text search misses conceptual paraphrases. The retrieval layer fuses both inside a PostgreSQL RPC function:

1. **Dense Vector Search**: Powered by `pgvector` with a Hierarchical Navigable Small World (HNSW) index using cosine distance:
   ```sql
   create index if not exists document_chunks_embedding_hnsw_idx
     on public.document_chunks using hnsw (embedding vector_cosine_ops)
     with (m = 16, ef_construction = 64);
   ```
2. **Lexical Full-Text Search**: Uses a stored generated `tsvector` column over chunk content with a Generalized Inverted Index (GIN):
   ```sql
   create index if not exists document_chunks_tsv_idx
     on public.document_chunks using gin(tsv_content);
   ```
3. **Reciprocal Rank Fusion (RRF)**: Dense and lexical candidate lists are fused directly in PostgreSQL using reciprocal rank scoring with smoothing factor $k = 60$:

$$\text{RRF\_Score}(d) = \sum_{m \in M} \frac{1}{k + r_m(d)}$$

Where $M = \{\text{dense}, \text{lexical}\}$ and $r_m(d)$ is the 1-based ordinal rank of document $d$ within search modality $m$.

### 4.3 Cross-Encoder Rescoring vs. Bi-Encoder Decay
Bi-encoder embedding models independently map the query and chunks into vector space:

$$\text{Score}_{\text{bi}}(q, d) = \mathbf{e}_q \cdot \mathbf{e}_d$$

Because this dot product cannot model fine-grained token-level cross-interactions, it suffers from severe position bias and false semantic matches. 

The retrieval pipeline passes the top-20 fused candidates to **FlashRank** (`ms-marco-TinyBERT-L-2-v2`), running locally on CPU via ONNX Runtime. The cross-encoder evaluates the concatenated token sequence $[\text{CLS}] \circ q \circ [\text{SEP}] \circ d$ with full cross-attention:

$$\text{Score}_{\text{cross}}(q, d) = \text{Transformer}([q; d])$$

This joint attention rescores the candidate set, filtering out false semantic positives and placing the most relevant passages at the top of the context window.

### 4.4 Distributed Transactional Outbox Engine
In distributed systems, updating a database and publishing an asynchronous event in two separate calls creates a dual-write vulnerability:

<p align="center">
  <img src="docs/diagrams/transactional_outbox.svg" alt="Transactional Outbox Dataflow & SKIP LOCKED" width="100%">
  <br>
  <em>Dual-write immunity boundary and SKIP LOCKED concurrent batch claiming.</em> &bull;
  <a href="docs/diagrams/transactional_outbox.html"><strong>Open Interactive Diagram Viewer ↗</strong></a>
</p>

To guarantee that document uploads are never orphaned or lost:
1. **Atomic Dual-Write Prevention**: The FastAPI endpoint commits document metadata, version staging, and an outbox record inside a **single ACID transaction** in PostgreSQL.
2. **Polling Dispatcher Daemon**: An asynchronous daemon continuously scans `private.job_dispatch_outbox` using PostgreSQL's concurrency-safe locking primitive:
   ```sql
   select id, payload from private.job_dispatch_outbox
   where dispatched_at is null and available_at <= now()
   order by available_at, id
   limit 10
   for update skip locked;
   ```
3. **Distributed Execution**: Claimed events are dispatched to Redis 8 and processed by Dramatiq worker threads. The worker executes PyPDF/Markdown normalization, semantic chunking, and local ONNX embedding generation (`BAAI/bge-small-en-v1.5`) with zero external API rate limits or latency dependencies.

### 4.5 Memory, Checkpointers & State Persistence

| Data Category | Persistence Target | Storage Invariant |
| :--- | :--- | :--- |
| **Document Vectors & Text Chunks** | PostgreSQL 16 (`pgvector`) | Persisted permanently to disk on the `postgres-data` Docker volume. Survives container restarts. |
| **Ingestion Queue & Outbox Jobs** | PostgreSQL Outbox + Redis 8 AOF | Persisted to PostgreSQL tables and Redis Append-Only File (`redis-broker-data`). |
| **Agent Thread Checkpoints** | In-Process Memory (`MemorySaver`) | By default, thread sessions live in API process RAM. Can be swapped for durable on-disk checkpoints (`SqliteSaver` or `PostgresSaver`) without code alterations: |

```python
from langgraph.checkpoint.sqlite import SqliteSaver
from rag_core.agent.graph import AdaptiveRagGraph

# Persist conversation sessions and state checkpoints durably to disk
with SqliteSaver.from_conn_string("checkpoints.db") as saver:
    agent = AdaptiveRagGraph(model=model, retriever=retriever, checkpointer=saver)
```

---

## 5. Capability Profiles: Dual Mock & Live Execution

The codebase implements a strict capability profile architecture separating offline developer workflows from active infrastructure runtimes:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                 CAPABILITY PROFILES                                    │
├──────────────────────────────────────────┬─────────────────────────────────────────────┤
│ 1. Lightweight / Mock Profile            │ 2. Live Runtime Profile                     │
│    (Deterministic Offline Verification)  │    (Active Infrastructure Execution)        │
├──────────────────────────────────────────┼─────────────────────────────────────────────┤
│ • In-Memory Test Fixtures                │ • PostgreSQL 16 pgvector HNSW Engine        │
│ • Mocked ChatModelPort & RetrieverPort   │ • PostgreSQL GIN Full-Text Search           │
│ • In-Process ASGI Transport (No Network) │ • Redis 8 Alpine + Dramatiq Worker Pool     │
│ • Zero API Keys / Zero Network Calls     │ • Live Groq LPU Inference (8B & 70B)        │
│ • 81 Tests Complete in <3 Seconds        │ • Live External Search (DuckDuckGo/Tavily)  │
└──────────────────────────────────────────┴─────────────────────────────────────────────┘
```

### 5.1 Lightweight / Mock Profile
The mock profile provides deterministic verification for continuous integration and local development without requiring Docker containers, database connections, or API credentials.
- **Port Abstractions**: Core domains interface strictly with abstract ports (`ChatModelPort`, `RetrieverPort`, `RerankerPort`, `WebSearchPort`, `JobQueue`).
- **In-Memory Fixtures**: Tests pass synthetic responses and deterministic chunk sets, ensuring unit and contract tests validate state transitions, routing logic, and HTTP serialization without network side-effects.
- **In-Process ASGI Execution**: Contract tests exercise FastAPI endpoints directly using `httpx.ASGITransport(app=app)`, verifying headers, status codes, and Server-Sent Event streaming protocols in-memory.

```python
from unittest.mock import AsyncMock
from uuid import uuid4
from rag_api.main import create_app
from rag_core.agent.graph import AdaptiveRagGraph, AgentState
from rag_core.config import AppSettings

# Instantiate API in lightweight test profile with zero external dependencies
mock_agent = AsyncMock(spec=AdaptiveRagGraph)
mock_agent.ainvoke.return_value = AgentState(
    query="Explain HNSW indexing",
    workspace_id=uuid4(),
    user_id=uuid4(),
    knowledge_base_ids=(uuid4(),),
    route="retrieve",
    answer="HNSW builds multi-layer graphs for logarithmic search.",
    status="answered",
)

app = create_app(AppSettings(_env_file=None), agent_graph=mock_agent)
```

### 5.2 Live Runtime Profile
The live profile operates in containerized or cloud environments, connecting concrete infrastructure adapters to the domain ports:
- **Groq LPU Client (`ChatGroqClient`)**: Dispatches inference prompts to Groq LPUs with strict JSON schema outputs for routing (`llama-3.1-8b-instant`) and streaming answer completions (`llama-3.3-70b-versatile`).
- **PostgreSQL Adapter (`AsyncConnectionPool`)**: Executes hybrid search RPCs and manages ACID transactional outbox rows via non-blocking connection pools.
- **Dramatiq + Redis 8 Broker**: Enqueues and consumes background ingestion jobs with distributed acknowledgment and retry policies.

---

## 6. Practical Failure Modes & Mitigations

```
┌──────────────────────────────────────┬────────────────────────────────────────────────────────┐
│ Real-World RAG Failure Mode          │ Structural Architectural Mitigation                    │
├──────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ Context Drift & Coreference          │ Fast LPU Query Condensation rewrites conversational    │
│ ("What did it say about X?")         │ pronouns into self-contained search queries.           │
├──────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ "Lost-in-the-Middle" Position Decay  │ FlashRank Cross-Encoder reranks top candidates via     │
│ (LLM ignores middle context chunks)  │ joint token attention, filtering out noise.            │
├──────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ Information Starvation               │ Corrective RAG (CRAG) router detects empty candidate   │
│ (Zero relevant chunks found in DB)   │ sets and triggers autonomous web search fallback.      │
├──────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ Dual-Write Inconsistency             │ PostgreSQL ACID Outbox commits document metadata and   │
│ (Upload succeeds, queue drops job)   │ event records simultaneously; SKIP LOCKED polls queue. │
├──────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ Hallucinated Citations               │ AST citation validation audits bracketed references    │
│ (Model fabricates sources [1], [2])  │ against verbatim chunk text and source UUIDs.          │
└──────────────────────────────────────┴────────────────────────────────────────────────────────┘
```

---

## 7. Execution Lifecycles

### Ingestion Lifecycle: From Raw File to Indexed Vector

<p align="center">
  <img src="docs/diagrams/ingestion_lifecycle.svg" alt="Ingestion Lifecycle Sequence" width="100%">
  <br>
  <em>End-to-end ingestion sequence from multipart file upload to HNSW vector index activation.</em> &bull;
  <a href="docs/diagrams/ingestion_lifecycle.html"><strong>Open Interactive Diagram Viewer ↗</strong></a>
</p>

### Query Lifecycle: Adaptive Routing & Synthesis

<p align="center">
  <img src="docs/diagrams/query_lifecycle.svg" alt="Query Lifecycle Sequence" width="100%">
  <br>
  <em>Adaptive query lifecycle with LPU condensation, hybrid RRF, cross-encoder reranking, and SSE token streaming.</em> &bull;
  <a href="docs/diagrams/query_lifecycle.html"><strong>Open Interactive Diagram Viewer ↗</strong></a>
</p>

---

## 8. Interactive Standalone Diagrams Gallery

In addition to static embedded figures, the repository includes 5 interactive standalone HTML diagrams in [`docs/diagrams/`](docs/diagrams/). Each diagram can be opened directly in any modern browser without web servers or build steps:

| Standalone Diagram Document | Technical Subject | Interactive Features |
| :--- | :--- | :--- |
| **[`docs/diagrams/system_topology.html`](docs/diagrams/system_topology.html)** | Multi-tier platform topology, network boundaries, and port mappings | Dark/Light theme toggle, SVG inspection, zoom, PDF export |
| **[`docs/diagrams/agent_stategraph.html`](docs/diagrams/agent_stategraph.html)** | Bounded LangGraph FSM transitions, conditional edges, state schema | Theme toggle, full `AgentState` schema data dictionary, branch traces |
| **[`docs/diagrams/ingestion_lifecycle.html`](docs/diagrams/ingestion_lifecycle.html)** | Transactional outbox staging, `SKIP LOCKED` polling, ONNX vectorization | Theme toggle, numbered sequence step tracking, actor boundaries |
| **[`docs/diagrams/query_lifecycle.html`](docs/diagrams/query_lifecycle.html)** | Adaptive condensation, hybrid RRF, cross-encoder, SSE token yield | Theme toggle, decision branch breakdown, candidate rescoring flow |
| **[`docs/diagrams/transactional_outbox.html`](docs/diagrams/transactional_outbox.html)** | Dual-write mitigation, exponential backoff, at-least-once invariants | Theme toggle, formal consistency invariants, error recovery logic |

### Opening Standalone Diagrams Locally
To open and inspect any diagram:
```bash
# Direct browser launch (Windows)
start docs/diagrams/system_topology.html

# Direct browser launch (macOS / Linux)
open docs/diagrams/system_topology.html # macOS
xdg-open docs/diagrams/system_topology.html # Linux

# Or serve the diagram directory via standard Python HTTP server
python -m http.server 8080 --directory docs/diagrams
# Then navigate to: http://localhost:8080/system_topology.html
```

---

## 9. Environment Configuration Reference

The platform resolves configuration through Pydantic BaseSettings (`rag_core.config.AppSettings`), reading environment variables prefixed with `RAG_` or standard aliases from `.env`:

| Environment Variable | Type | Default Value | Secret? | Required Profile | Purpose & Invariants |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `GROQ_API_KEY` | `SecretStr` | *None* | **Yes** | Live Runtime | Server-only credential for Groq LPU inference. Never exposed to browser or frontend clients. |
| `RAG_GROQ_FAST_MODEL` | `str` | `llama-3.1-8b-instant` | No | Live Runtime | High-speed model for query condensation, intent classification, and structured outputs (<150ms). |
| `RAG_GROQ_QUALITY_MODEL` | `str` | `llama-3.3-70b-versatile` | No | Live Runtime | High-capacity model for grounded context synthesis and citation generation. |
| `RAG_GROQ_AGENT_MODEL` | `str` | `llama-3.3-70b-versatile` | No | Live Runtime | Tool-calling model for bounded StateGraph agent steps. |
| `RAG_DATABASE_URL` | `str` | `postgresql://postgres:postgres@127.0.0.1:54322/postgres` | **Yes** (Remote) | Live Runtime | PostgreSQL connection URL. Must point to an instance with `pgvector` and migrations applied. |
| `RAG_REDIS_BROKER_URL` | `str` | `redis://127.0.0.1:6379/0` | **Yes** (Remote) | Live Runtime | Connection string for Redis 8 broker transporting Dramatiq ingestion messages. |
| `RAG_ENVIRONMENT` | `str` | `local` | No | All Profiles | Operational runtime mode: `local`, `test`, `staging`, or `production`. |
| `RAG_LOG_LEVEL` | `str` | `INFO` | No | All Profiles | Minimum logging threshold: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. |
| `RAG_JSON_LOGS` | `bool` | `false` | No | All Profiles | When `true`, outputs structured JSON logs suitable for log aggregators (Datadog, Loki, CloudWatch). |
| `RAG_ACTIVE_READINESS_PROBES` | `bool` | `false` | No | Live Runtime | When `true`, `/health/ready` executes active TCP/socket probes to PostgreSQL and Redis. |
| `RAG_SUPABASE_URL` | `str` | `http://127.0.0.1:54321` | No | Live / Supabase | Base URL of the Supabase API or local CLI gateway. |
| `RAG_SUPABASE_PUBLISHABLE_KEY` | `SecretStr` | *None* | Public | Optional | Client-safe publishable key for frontend Auth interaction. Does not bypass PostgreSQL RLS. |
| `RAG_SUPABASE_SECRET_KEY` / `JWT_SECRET` | `SecretStr` | *None* | **Yes** | Auth Validation | Backend secret used to verify cryptographic HS256/RS256 signatures on client JWT tokens. |
| `WEB_SEARCH_PROVIDER` | `str` | `duckduckgo` | No | Live Fallback | Active search provider for CRAG fallback: `duckduckgo`, `tavily`, or `exa`. |
| `TAVILY_API_KEY` | `SecretStr` | *None* | **Yes** | Tavily Search | Server-only API key required when `WEB_SEARCH_PROVIDER=tavily`. |
| `EXA_API_KEY` | `SecretStr` | *None* | **Yes** | Exa Search | Server-only API key required when `WEB_SEARCH_PROVIDER=exa`. |
| `LANGSMITH_TRACING` | `bool` | `false` | No | Observability | When `true`, exports LangGraph execution traces to LangSmith for evaluation and inspection. |
| `LANGSMITH_API_KEY` | `SecretStr` | *None* | **Yes** | Observability | Server-only API key for LangSmith trace reporting. |

---

## 10. Repository Layout

The repository is structured as a typed monorepo managed with [`uv`](https://docs.astral.sh/uv/):

```
.
├── apps/
│   ├── api/                           # rag-api: FastAPI HTTP & SSE service
│   │   ├── src/rag_api/
│   │   │   ├── main.py                # Route definitions & dependency injection
│   │   │   └── templates/index.html   # Zero-dependency SSE web console
│   │   └── pyproject.toml
│   └── worker/                        # rag-worker: Dramatiq worker & Dispatcher
│       ├── src/rag_worker/
│       │   ├── app.py                 # Redis broker configuration & Dramatiq actors
│       │   ├── dispatcher.py          # FOR UPDATE SKIP LOCKED outbox polling daemon
│       │   └── tasks/ingestion.py     # Parsing, chunking, and ONNX vector embedding
│       └── pyproject.toml
├── packages/
│   └── core/                          # rag-core: Hexagonal domain ports & services
│       ├── src/rag_core/
│       │   ├── agent/graph.py         # Bounded LangGraph Adaptive RAG StateGraph
│       │   ├── auth/                  # RS256/HS256 JWT verifier & workspace security
│       │   ├── ingestion/             # PyPDF & Markdown parsers, chunking strategies
│       │   ├── jobs/outbox.py         # Outbox repository & ACID transaction helpers
│       │   └── retrieval/             # Hybrid RRF, FlashRank reranking, query condenser
│       └── pyproject.toml
├── docs/
│   ├── LEARNING_JOURNAL.md            # 13-chapter educational systems engineering textbook
│   ├── adr/                           # 12 Architecture Decision Records (001 to 012)
│   ├── configuration/                 # Service & environment variable specifications
│   └── diagrams/                      # 5 Interactive standalone HTML architecture diagrams
│       ├── system_topology.html
│       ├── agent_stategraph.html
│       ├── ingestion_lifecycle.html
│       ├── query_lifecycle.html
│       └── transactional_outbox.html
├── supabase/migrations/               # PostgreSQL schema DDL, HNSW index, RRF RPC functions
├── tests/
│   ├── contract/                      # HTTP API contract tests (Agent, Ingestion, Chat, Health)
│   └── unit/                          # Component unit tests (Graph, Reranker, Outbox, Parsers)
├── docker-compose.yml                 # Self-contained multi-service local infrastructure
├── pyproject.toml                     # Root uv workspace configuration
└── uv.lock                            # Deterministic frozen lockfile
```

---

## 11. Local Infrastructure & Reproduction

### Deployment Option 1: Standalone Docker Compose (Zero Cloud Setup)

The stack runs locally with PostgreSQL 16 (pgvector), Redis 8 Alpine, FastAPI, the Dramatiq Worker, and the Outbox Dispatcher. The only external requirement is a free [Groq API Key](https://console.groq.com/keys) for LPU inference.

```bash
# 1. Clone repository
git clone https://github.com/Courage-7/RAG-Agent.git
cd RAG-Agent

# 2. Configure environment
cp .env.example .env
# Edit .env and supply: GROQ_API_KEY=gsk_...

# 3. Spin up all 5 infrastructure services
docker compose up -d

# 4. Access the interactive web console
# Open your browser to: http://localhost:8000/
```

### Deployment Option 2: Native Development with `uv`

```bash
# 1. Install workspace dependencies
uv sync

# 2. Terminal 1: Run FastAPI Web Service
uv run fastapi dev apps/api/src/rag_api/main.py

# 3. Terminal 2: Run Outbox Dispatcher Daemon
uv run python -m rag_worker.dispatcher

# 4. Terminal 3: Run Dramatiq Worker Pool
uv run --package rag-worker dramatiq rag_worker.app
```

---

## 12. Verification & Quality Assurance Tooling

The codebase enforces strict static typing, deterministic linting, secret scanning, and automated test coverage across all workspace packages:

```bash
# 1. Execute automated test suite (81 unit and contract tests)
uv run pytest tests -q

# 2. Run strict MyPy static type checking across all packages
uv run mypy apps packages tests

# 3. Verify code formatting and lint rules via Ruff
uv run ruff check .
uv run ruff format --check .

# 4. Verify automated secret prevention (Gitleaks)
gitleaks detect --source . --verbose

# 5. Execute Jupyter validation notebook in-process
uv run jupyter execute --inplace --timeout=60 notebooks/rag_demo.ipynb
```

---

## 13. HTTP & SSE API Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/` | Serves the interactive full-stack web console |
| `GET` | `/health/live` | Non-blocking service liveness probe |
| `GET` | `/health/ready` | Active socket health probes for PostgreSQL, Redis, and Groq |
| `POST` | `/v1/agent/stream` | Server-Sent Events stream from the Adaptive LangGraph agent |
| `POST` | `/v1/agent/query` | Synchronous execution of the Adaptive LangGraph agent |
| `POST` | `/v1/chat/stream` | Token streaming from Hybrid RRF + FlashRank reranking |
| `POST` | `/v1/query` | Synchronous grounded retrieval query execution |
| `POST` | `/v1/documents/upload` | Multipart file intake for `.pdf`, `.md`, and `.txt` documents |
| `POST` | `/v1/documents` | JSON document ingestion for raw text payloads |

---

## 14. Educational Engineering Resources

- **[`docs/LEARNING_JOURNAL.md`](docs/LEARNING_JOURNAL.md)**: A 13-chapter engineering guide detailing vector indexing mathematics, HNSW graph complexity, RRF derivation, lost-in-the-middle mitigations, and distributed transaction semantics.
- **[`docs/adr/`](docs/adr/)**: 12 Architecture Decision Records documenting key design decisions (Bounded Agents, Hybrid Baselines, Capability Profiles, Transactional Outbox, and Checkpoint Security).
- **[`docs/diagrams/`](docs/diagrams/)**: 5 interactive standalone HTML diagrams with light/dark themes and SVG inspection.
- **[`docs/configuration/credentials-and-services.md`](docs/configuration/credentials-and-services.md)**: Configuration guide for every service, port, secret, and environment variable.
