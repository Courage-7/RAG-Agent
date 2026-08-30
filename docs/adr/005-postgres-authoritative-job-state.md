# ADR-005: PostgreSQL is authoritative for job state

- Status: Accepted
- Date: 2026-08-29

## Context

Broker state is transient and insufficient for user-visible progress, cancellation, recovery, audit, and deduplication.

## Decision

Store lifecycle, stage, attempts, leases, heartbeats, cancellation intent, safe failures, and idempotency keys in `public.ingestion_jobs`. Redis messages contain only the job identifier and versioned routing fields. State changes use an explicit transition table and compare-and-set conditions; terminal jobs cannot restart.

## Consequences

Postgres can explain and recover every job even after broker loss. Workers incur database traffic for claims and heartbeats. Failure messages must be sanitized and may not contain source text, credentials, or raw provider responses.
