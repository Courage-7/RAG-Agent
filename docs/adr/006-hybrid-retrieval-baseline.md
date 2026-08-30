# ADR-006: Hybrid retrieval baseline

- Status: Accepted
- Date: 2026-08-29

## Context

Dense retrieval misses exact identifiers and rare terms; lexical retrieval misses paraphrases. Advanced RAG cannot be judged without a strong, understandable baseline.

## Decision

The first production candidate combines tenant-filtered dense and PostgreSQL full-text candidate sets, fuses ranks with reciprocal-rank fusion, optionally expands structural neighbors, reranks a bounded set, and returns citation-ready evidence. Authorization filters execute inside each retrieval query, never as post-filtering.

## Consequences

The baseline handles semantic and exact-match queries and remains diagnosable. It introduces multiple retrieval scores, so raw, fused, and reranked positions are retained for evaluation and traces.
