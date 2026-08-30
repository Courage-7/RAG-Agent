# ADR-003: Redis and Dramatiq for background execution

- Status: Provisional
- Date: 2026-08-29

## Context

Parsing, OCR, chunking, embedding, and repair exceed request lifetimes. FastAPI in-process background tasks do not provide the required durability or resource separation.

## Decision

Use Dramatiq with a private, persistence-enabled Redis broker for the first worker implementation. Redis transports identifiers only; Postgres remains authoritative. PGMQ was not selected initially because a dedicated worker broker provides familiar retry and routing mechanics, but it remains the preferred simplification if the extra service does not earn its operational cost.

## Validation gate

Before production, prove redelivery, duplicate suppression, retry exhaustion, worker termination, Redis restart, graceful shutdown, regional placement, and acceptable RPO/RTO and cost. Failure of this gate triggers a new ADR selecting PGMQ or another `JobQueue` adapter.
