# ADR-011: API, worker, and graph boundaries

- Status: Accepted
- Date: 2026-08-29

## Context

HTTP serving, document processing, and conversational orchestration have different scaling, failure, and latency characteristics.

## Decision

FastAPI validates identity and input, streams interactive responses, and commits job intent. Dramatiq workers perform long-running ingestion and repair. LangGraph coordinates bounded retrieval/agent state but does not replace the durable ingestion job machine. FastAPI Cloud is the target API host; a separately validated runtime hosts workers.

## Consequences

API deployments remain responsive and independently scalable. Cross-process traces and typed contracts are mandatory. Production worker hosting stays an explicit Milestone 0 spike rather than an assumption about FastAPI Cloud background lifecycles.
