# ADR-007: Evaluation-gated advanced retrieval

- Status: Accepted
- Date: 2026-08-29

## Context

Multi-query, decomposition, HyDE, contextual retrieval, RAPTOR, GraphRAG, and late interaction can improve selected workloads while increasing latency, cost, and failure modes.

## Decision

No advanced strategy becomes a default from intuition alone. Each is a registered strategy behind the retrieval port and must beat the hybrid baseline on a versioned representative dataset while meeting latency, cost, citation, security, and regression budgets. Adaptive routing must also outperform always-baseline and always-advanced policies.

## Consequences

The system may use fewer fashionable techniques, but every promoted technique has measured value. Evaluation fixtures, experiment metadata, and rollback configuration become product infrastructure.
