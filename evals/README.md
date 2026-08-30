# Evaluation workspace

Evaluation is a release gate, not a notebook-only activity. Versioned datasets live under `datasets/`; runners and metric adapters will live under `src/` when the first hybrid baseline is implemented.

The first dataset must cover answerable and unanswerable knowledge questions, exact identifiers, multi-document synthesis, stale/conflicting evidence, citation correctness, cross-tenant attempts, prompt injection, tool selection, approval behavior, and job recovery. Do not promote an advanced retrieval strategy without comparing it against the same frozen baseline split.
