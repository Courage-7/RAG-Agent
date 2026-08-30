# ADR-008: Capability profiles instead of provider names

- Status: Accepted
- Date: 2026-08-29

## Context

Hard-coding model names across graphs makes changes unsafe and confuses capability requirements with vendors.

## Decision

Call models, embeddings, rerankers, and retrievers through typed ports and named profiles. Groq is the initial LLM provider. Initial aliases are `fast_structured` (`openai/gpt-oss-20b`), `quality` (`openai/gpt-oss-120b`), and `agent` (`openai/gpt-oss-120b`); they are candidates until benchmarked. Structured decisions require strict JSON Schema support. Profiles carry limits, timeout, retries, price assumptions, and capability flags.

## Consequences

Configuration can change mappings without changing graph code, and tests can use fakes. Portability does not mean implementing several providers now. A new provider requires contract and evaluation parity before failover is claimed.
