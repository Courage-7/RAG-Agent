# ADR-001: Deterministic RAG and bounded agents

- Status: Accepted
- Date: 2026-08-29

## Context

Knowledge questions need predictable retrieval, citations, latency, and cost. Connected tools need planning, but unconstrained agent loops amplify prompt injection, side effects, and runaway spend.

## Decision

Use a deterministic retrieval graph for normal Q&A. Route to a bounded LangGraph agent only when the request requires a tool or a multi-step operation. Every agent run has step, tool-call, elapsed-time, token, and cost budgets. Exhaustion produces a typed partial/abstention result; it never silently expands the budget.

## Consequences

The common path is testable and replayable. Agent flexibility is deliberately limited. Routing and trajectories must be evaluated separately from retrieval quality.
