# ADR-009: Versioned index activation

- Status: Accepted
- Date: 2026-08-29

## Context

Changing parsers, chunkers, enrichers, embeddings, or vector dimensions can silently mix incompatible representations and corrupt retrieval quality.

## Decision

Every document version and chunk records parser, normalization, chunking, enrichment, embedding, and pipeline versions. Build a new index generation beside the active generation, verify completeness and evaluation gates, then atomically activate it per knowledge base. Never overwrite the only active representation in place.

## Consequences

Reindexing supports audit and rollback. Parallel generations temporarily consume more storage and need lifecycle cleanup. The first milestone defines version fields without operating multiple production indexes prematurely.
