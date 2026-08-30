# Job recovery runbook

This runbook defines the intended Milestone 1 recovery behavior. Commands and automated drills are added with the outbox dispatcher.

## Authority and invariants

- PostgreSQL `ingestion_jobs` is authoritative; Redis is transport only.
- A missing Redis message does not mean a job is complete or absent.
- Delivery is at least once. Replaying the same job must not duplicate an external or indexing effect.
- Only an expired lease may be reclaimed. A terminal job may not restart.
- Queue payloads contain identifiers and routing metadata, never document content or credentials.

## Triage order

1. Check API and worker deployment health and trace identifiers.
2. Measure pending outbox age, queued jobs, expired leases, retry-scheduled jobs, and dead-letter count.
3. Restore the Redis broker if unavailable; do not rewrite Postgres state to imitate delivery.
4. Run the reconciler to release expired outbox claims and job leases.
5. Republish only undispatched outbox rows and eligible jobs.
6. Verify idempotency records and document/index activation before declaring recovery complete.

## Cancellation

Cancellation is cooperative. The API records `cancel_requested_at`; workers check between durable stages, stop before the next side effect, release leases, and transition to `cancelled`. Killing a worker alone is not a cancellation mechanism.

## Escalate rather than replay when

- the same idempotency key refers to different immutable inputs;
- a job appears terminal but the active index or artifact state disagrees;
- a failure message may contain secret or document data;
- Redis loss exceeds the accepted production RPO/RTO;
- tenant identity or authorization cannot be reconstructed from authoritative records.
