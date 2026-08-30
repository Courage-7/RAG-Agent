# Foundation implementation status

Updated: 2026-08-29

## Completed and locally verified

- Python 3.12 `uv` workspace with locked dependencies and isolated API, worker, and core packages.
- Typed job, model, retrieval, grounded-response, and side-effect approval contracts.
- Groq `ChatGroq` adapter with capability profiles, strict JSON-schema mode, streaming normalization, usage/request metadata, and typed provider failures.
- FastAPI liveness/readiness skeleton and structured logging with secret-bearing settings represented by redacted `SecretStr` values.
- Dramatiq queue port/adapter, versioned small-envelope contract, and demo actor.
- Twelve architecture decision records.
- Credential-free foundation notebook covering model profiles, job and evidence contracts, exact
  side-effect approvals, the Groq adapter, and in-process FastAPI health checks.
- Unit and API contract suite: 24 tests passing.
- Ruff formatting/lint and strict MyPy checks passing.
- Immutable `uv.lock` and SHA-pinned GitHub Actions workflow.
- Obsolete Streamlit/FAISS prototype source removed after explicit replacement approval.

## Implemented but awaiting Docker validation

- Persistence-enabled Redis Compose service and separate API/worker containers.
- Supabase CLI configuration, private documents bucket configuration, job/outbox migration, RLS/grant pgTAP tests, and database CI job.

Docker is unavailable in the current WSL environment, so the local Supabase reset, pgTAP execution, Redis dispatch, container build, and restart-recovery drill remain unverified here. Enable Docker Desktop WSL integration before treating these paths as proven.

## Next vertical slice

1. Add repositories and SQL operations that atomically create `ingestion_jobs` plus outbox rows.
2. Add dispatcher claims, publish acknowledgement, expired-claim reconciliation, and cooperative cancellation.
3. Exercise duplicate delivery, Redis restart, worker termination, retry exhaustion, and cancellation.
4. Add an opt-in live Groq smoke test for structured and streamed calls, then record model latency, schema validity, token usage, and 429 behavior.
5. Begin Milestone 2 with Supabase OTP identity, workspaces/memberships, JWT verification, and tenant RLS.

The full RAG graph, ingestion pipeline, embeddings, hybrid retrieval, LangGraph agent, and Composio tools intentionally remain behind these foundation gates.
