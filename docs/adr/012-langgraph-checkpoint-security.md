# ADR-012: LangGraph checkpoint security and retention

- Status: Provisional
- Date: 2026-08-29

## Context

Checkpoints enable resumable approval and multi-step flows but can persist prompts, retrieved text, tool results, and identifiers beyond their intended lifetime.

## Decision

Use a dedicated Postgres checkpoint schema and least-privilege runtime role. Checkpoint state stores references and redacted summaries where possible, never connector credentials. Thread ownership is bound to workspace and user authorization on every resume. Apply per-flow retention and deletion, encrypt platform storage, and trace identifiers rather than full checkpoint payloads.

## Validation gate

Before enabling production persistence, pin a LangGraph checkpoint package/schema version and prove tenant isolation, approval resume, concurrent update behavior, pruning, deletion, backup restore, and sensitive-field redaction.

## Consequences

Resumability does not create an unbounded shadow data store. Some flows may need to refetch evidence after retention expires. Exact schema and retention periods remain open until the spike and compliance requirements are complete.
