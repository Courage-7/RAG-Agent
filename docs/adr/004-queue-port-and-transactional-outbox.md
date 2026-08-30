# ADR-004: Queue port and transactional outbox

- Status: Accepted
- Date: 2026-08-29

## Context

Writing durable job state and publishing to Redis is a dual write. Either side can succeed alone, producing lost or orphaned work.

## Decision

Domain services depend on a typed `JobQueue` port. Creating a job also creates an identifier-only outbox row in the same Postgres transaction. A dispatcher claims pending rows, publishes idempotent envelopes, and records the transport identifier. A reconciler releases expired claims and republishes undispatched work.

## Consequences

Broker replacement does not rewrite ingestion logic and database commits cannot lose dispatch intent. Delivery is at least once, so every actor and stage transition must be idempotent. The outbox adds a dispatcher, reconciliation, and lag monitoring.
