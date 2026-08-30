# ADR-010: Approval and idempotency for side-effecting tools

- Status: Accepted
- Date: 2026-08-29

## Context

Composio connectors can read external data or perform irreversible writes. Retrieved content and tool output are untrusted, and agent retries can duplicate effects.

## Decision

Classify each tool as read-only or side-effecting. Read-only tools may run within policy and budget. Writes require a server-generated preview, explicit human approval bound to the user, workspace, arguments hash, expiry, and idempotency key. Execution re-authorizes the connection and arguments after approval. Secrets and provider tokens remain server-side.

## Consequences

Calendar and other writes are slower but auditable and retry-safe. Composio supplies connector execution, not application authorization. Tool calls, approvals, denials, and sanitized results are retained in an audit trail.
