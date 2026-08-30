# Code Quality Gate Skill

## Purpose

Act as a production-grade code audit and maintainability gate after every code-changing task.

This skill combines:
- senior/staff-level code review,
- SonarQube-style maintainability inspection,
- architecture-boundary review,
- static-analysis awareness,
- security review,
- duplication analysis,
- naming review,
- typing/error-handling review,
- and test-readiness verification.

The objective is not merely to make code "look clean."

The objective is to ensure the codebase remains:
- correct,
- maintainable,
- testable,
- observable,
- secure,
- appropriately abstracted,
- free of unjustified duplication,
- free of obvious architectural drift,
- and production-ready.

This skill is a mandatory quality gate before commit preparation.

---

## Core Rule

Never approve code because it "looks fine."

Evidence should come from:
1. the actual diff,
2. surrounding implementation context,
3. repository conventions,
4. architecture boundaries,
5. tests,
6. lint/type/static-analysis output where available.

If deterministic tooling exists, run it.

If deterministic tooling does not exist, explicitly note that the corresponding check was manual.

---

# 1. Severity Levels

Classify findings using:

```text
BLOCKER
HIGH
MEDIUM
LOW
INFO
```

## BLOCKER

Use for issues that must be fixed before merge or commit completion.

Examples:
- security vulnerability,
- cross-tenant data leakage,
- authorization bypass,
- destructive behavior without approval,
- invalid transaction semantics,
- data corruption risk,
- broken public contract,
- critical race condition,
- hard-coded secret,
- retry behavior that can duplicate destructive side effects,
- code that cannot run.

## HIGH

Use for serious design or reliability defects.

Examples:
- architectural boundary violation,
- duplicated authorization logic with inconsistent behavior,
- unbounded concurrency,
- blocking I/O inside critical async paths,
- swallowed exceptions,
- incorrect idempotency,
- non-deterministic side effects,
- large-scale duplicated business logic,
- type contract violations,
- missing tests for critical behavior.

## MEDIUM

Use for maintainability or clarity issues that should be fixed before the feature is considered polished.

Examples:
- oversized functions,
- deep nesting,
- mixed responsibilities,
- long parameter lists,
- confusing naming,
- excessive conditional complexity,
- leaky abstractions,
- poor module cohesion,
- repeated validation logic,
- weak error taxonomy.

## LOW

Use for local quality improvements.

Examples:
- minor naming weakness,
- avoidable helper duplication,
- small readability issues,
- unnecessary comments,
- minor formatting inconsistency not caught by tooling.

## INFO

Use for optional or future-facing observations.

Examples:
- possible abstraction opportunity that is not yet justified,
- performance optimization not currently needed,
- refactor candidate that should wait for more evidence.

---

# 2. Audit Order

Review in this order:

1. Correctness
2. Security
3. Authorization / tenant isolation
4. Data integrity
5. Architecture boundaries
6. Concurrency / async behavior
7. Error handling
8. Idempotency / retry safety
9. Duplication
10. Naming
11. Cohesion / responsibility
12. Typing
13. Tests
14. Observability
15. Performance
16. Dead code / unnecessary abstractions
17. General maintainability

Do not start with style if correctness or architecture is broken.

---

# 3. Architecture Boundary Audit

Respect the architecture defined by the repository.

For this project, treat the following as expected high-level boundaries unless the repository explicitly changes them through an ADR.

## FastAPI

FastAPI owns:
- HTTP contracts,
- request validation,
- authentication boundary,
- SSE/streaming transport,
- CRUD endpoints,
- orchestration entrypoints,
- status endpoints.

FastAPI routes must not:
- perform heavy document parsing,
- perform long-running embedding work,
- contain raw persistence logic,
- contain Redis implementation details,
- directly embed major business workflows.

## LangGraph

LangGraph owns:
- AI orchestration,
- deterministic RAG graph,
- bounded research/tool workflows,
- retrieval escalation,
- human-in-the-loop state,
- bounded model/tool execution.

LangGraph must not:
- act as the system job queue,
- own durable application authorization,
- directly encode infrastructure-specific persistence where a port exists,
- decide permissions.

## Redis

Redis owns transient infrastructure:
- queue broker,
- cache,
- short-lived locks,
- transient coordination,
- rate limiting,
- deduplication keys.

Redis must not be the authoritative source of:
- users,
- documents,
- job lifecycle,
- tenant permissions,
- audit history,
- conversations,
- tool access,
- vector data.

## Dramatiq

Dramatiq owns:
- background job dispatch,
- worker execution,
- queue routing,
- retry dispatch.

Dramatiq must not:
- become the AI workflow engine,
- contain HTTP-specific behavior,
- become the source of truth for business state.

## Supabase / PostgreSQL

PostgreSQL owns durable application state.

Examples:
- users/profile references,
- workspaces,
- memberships,
- knowledge bases,
- documents,
- document versions,
- chunks,
- ingestion_jobs,
- conversations,
- tool runs,
- audit events,
- evaluation data.

## Authorization

Authorization must be deterministic.

Never accept:
```text
"The model decided the user has access."
```

Authorization belongs in:
- RLS,
- deterministic service logic,
- policy modules,
- verified claims,
- explicit access-control checks.

## Tools / Composio

Tool use must obey:
- explicit allowed tools,
- account pinning where needed,
- read/write classification,
- approval rules,
- idempotency rules,
- timeout and retry policies,
- local authorization policy.

---

# 4. Code Smells

Inspect for both obvious and structural smells.

## Functions

Flag:
- large functions,
- multiple unrelated responsibilities,
- deep nesting,
- complex branching,
- implicit side effects,
- too many parameters,
- boolean control flags,
- hidden state mutation,
- repeated exception translation,
- repeated validation,
- unclear return semantics.

A function should usually have one coherent responsibility.

Do not enforce arbitrary line-count thresholds mechanically. Use complexity and cohesion.

## Classes

Flag:
- god objects,
- classes coordinating unrelated domains,
- excessive mutable state,
- unnecessary inheritance,
- classes that merely wrap unrelated helpers,
- feature envy,
- stateful service singletons without justification.

## Modules

Flag:
- unrelated concepts in one file,
- circular imports,
- ambiguous module boundaries,
- infra code mixed with domain logic,
- duplicate modules with overlapping responsibilities.

## Control Flow

Flag:
- excessive nesting,
- duplicated conditionals,
- exception-driven normal control flow,
- broad catch-all handling,
- unreachable branches,
- retry loops without clear bounds.

## State

Flag:
- mutable global state,
- hidden caches,
- state mutation across layers,
- implicit shared state,
- non-thread-safe shared objects.

---

# 5. Duplication Audit

Look beyond literal copy/paste.

Detect duplicated:

- business rules,
- authorization checks,
- validation,
- SQL,
- retry logic,
- exception mapping,
- configuration,
- provider/model selection,
- response construction,
- serialization,
- observability instrumentation,
- tool policy logic,
- idempotency logic,
- cache-key construction.

Do not blindly DRY code.

Use this decision model:

```text
duplication detected
        ↓
is it the same stable concept?
        │
   ┌────┴────┐
   │         │
  yes        no
   │         │
abstract   keep separate
```

Do not introduce abstraction for accidental similarity.

Prefer a small amount of duplication over a bad abstraction.

---

# 6. Naming Audit

Names should describe responsibility clearly.

## Reject vague names unless genuinely justified

Examples to challenge:

```text
utils.py
helpers.py
common.py
misc.py
stuff.py
manager.py
processor.py
handler.py
service2.py
temp.py
base.py
core_utils.py
```

These names are not always forbidden, but require justification.

Prefer names like:

```text
embedding_service.py
retrieval_policy.py
document_parser.py
ingestion_repository.py
tool_authorization.py
citation_verifier.py
job_queue.py
dramatiq_redis.py
workspace_policy.py
```

Rule:

> A filename should communicate its responsibility without requiring the reader to open it.

## Symbols

Flag:
- single-letter names outside tight loops/math,
- names that describe implementation instead of intent,
- misleading plural/singular naming,
- inconsistent terminology,
- overloaded terms,
- ambiguous acronyms,
- `data`, `item`, `obj`, `thing`, `result` when a domain name exists.

---

# 7. File and Package Structure

Review for:

- cohesive feature boundaries,
- sensible package depth,
- avoidable nesting,
- giant cross-domain modules,
- duplicate modules,
- circular dependencies,
- orphan files,
- dead packages,
- infrastructure leaking into domain packages,
- tests not mirroring meaningful behavior.

Do not create folders purely for aesthetic symmetry.

Prefer feature-based cohesion over artificial technical-layer fragmentation where appropriate.

---

# 8. Python-Specific Audit

Inspect for:

## Typing

Flag:
- excessive `Any`,
- missing return types on public/internal contracts,
- implicit `Optional`,
- untyped provider/adapter boundaries,
- broad dictionaries where typed models are appropriate,
- inconsistent Pydantic/domain schemas,
- unsafe casts.

Prefer:
- Protocols for ports,
- dataclasses/Pydantic/domain models where justified,
- explicit return types,
- typed error models.

## Async

Flag:
- blocking calls in async paths,
- synchronous HTTP/database clients inside async request handlers,
- missing awaits,
- unbounded `gather`,
- async wrappers around purely synchronous code without value,
- hidden threadpool dependence,
- fire-and-forget tasks without ownership.

## Exceptions

Flag:
- `except Exception: pass`,
- bare `except`,
- swallowed exceptions,
- logging then silently continuing when correctness requires failure,
- user-facing internal stack details,
- generic errors where typed errors are expected,
- retrying permanent failures.

## Defaults

Flag:
- mutable defaults,
- module-level mutable config,
- shared default objects.

## Resource handling

Verify:
- files,
- sessions,
- DB transactions,
- streams,
- subprocesses,
- clients,
- temporary files

are closed or scoped correctly.

---

# 9. Security Audit

Inspect touched code for:

- hard-coded secrets,
- token leakage,
- unsafe logs,
- path traversal,
- insecure temporary files,
- shell injection,
- SQL injection,
- missing parameterization,
- unvalidated URLs,
- SSRF risk,
- unsafe deserialization,
- cross-tenant access,
- privilege escalation,
- insecure defaults,
- overly broad service-role usage,
- missing RLS assumptions,
- exposed provider credentials,
- prompt/tool injection paths.

Security-sensitive changes should receive additional scrutiny.

---

# 10. Multi-Tenant Audit

For any tenant-scoped operation, verify:

- `workspace_id` / tenant context is explicit,
- authorization is checked before data access,
- queries are tenant-filtered,
- caches are tenant-safe,
- vector retrieval cannot cross tenant boundaries,
- background jobs preserve tenant identity,
- tool connections are user/workspace scoped,
- logs do not leak another tenant's data.

Cross-tenant leakage is always a BLOCKER.

---

# 11. Retry and Idempotency Audit

For background jobs and external tool calls, verify:

- retries are bounded,
- permanent vs transient failures are classified,
- retry backoff exists where appropriate,
- side effects are idempotent,
- duplicate queue delivery is safe,
- document activation is transactional,
- destructive tool calls are not retried blindly,
- idempotency keys are stable.

A worker must assume duplicate delivery can happen.

---

# 12. Transaction Audit

Check multi-step writes for:

- atomicity,
- partial failure,
- stale updates,
- lost updates,
- incorrect commit order,
- missing rollback,
- inconsistent state across queue/database/storage.

Where state transitions matter, make them explicit.

---

# 13. Test Audit

Tests must verify behavior, not implementation trivia.

Check:

- happy path,
- invalid input,
- authorization,
- tenant isolation,
- retries,
- idempotency,
- failure handling,
- state transitions,
- cancellation,
- duplicate delivery,
- provider failures,
- malformed tool output,
- timeouts,
- regression coverage for fixed bugs.

Avoid:
- tests coupled to private implementation details,
- tests that only assert mocks were called,
- duplicate tests with no additional behavioral value.

Critical bug fixes should include regression tests where practical.

---

# 14. Observability Audit

Touched production paths should emit useful structured context.

Check for appropriate identifiers such as:

```text
trace_id
request_id
job_id
conversation_id
workspace_id
document_id
document_version_id
```

where relevant.

Verify logs:
- do not contain secrets,
- are structured,
- have meaningful severity,
- are not noisy,
- provide enough diagnostic context.

Check whether important operations expose timing/failure metrics.

---

# 15. Performance Audit

Do not micro-optimize prematurely.

Check for obvious production issues:

- N+1 queries,
- repeated model calls,
- repeated embedding computation,
- repeated network calls,
- blocking I/O,
- loading entire large files into memory unnecessarily,
- unbounded context growth,
- unbounded list accumulation,
- missing pagination,
- repeated serialization of large payloads,
- poor batching.

Only mark optimization findings HIGH when they create clear production risk.

---

# 16. Dead Code and Unnecessary Abstraction

Flag:
- unused classes,
- unused functions,
- abandoned feature flags,
- dead configuration,
- commented-out code,
- speculative interfaces with one trivial implementation and no architectural value,
- placeholder modules with no responsibility.

Do not keep dead code "for later."

Git is the history.

---

# 17. Tooling

Discover repository tooling before inventing commands.

If configured, run appropriate checks.

Common Python examples:

```text
ruff check .
ruff format --check .
pyright
pytest
coverage
pip-audit
```

Optional tools if the repo actually uses them:

```text
mypy
semgrep
bandit
vulture
radon
xenon
```

Do not install new tooling silently.

If a required tool is absent:
- state that it was not available,
- complete the manual audit,
- recommend it separately if justified.

---

# 18. Quality Gate Procedure

After implementation:

1. Inspect `git status`.
2. Inspect the complete diff.
3. Read surrounding code for changed behavior.
4. Identify architecture boundaries involved.
5. Run configured formatter/linter.
6. Run configured static type checker.
7. Run relevant unit/integration tests.
8. Run dependency/security checks where configured.
9. Audit duplication and naming manually.
10. Audit error handling.
11. Audit concurrency/idempotency if applicable.
12. Audit security and tenant isolation.
13. Audit test adequacy.
14. Categorize findings by severity.
15. Fix BLOCKER and HIGH findings.
16. Re-run checks after fixes.
17. Do not mark the task complete until the gate passes.

MEDIUM findings should normally be resolved before commit unless:
- they are intentionally deferred,
- the reason is explicit,
- and they do not compromise correctness/security/architecture.

LOW and INFO findings may be documented.

---

# 19. Gate Result Format

Always finish with:

```text
QUALITY GATE

Correctness: PASS | FAIL
Architecture: PASS | FAIL
Security: PASS | FAIL
Tenant Isolation: PASS | FAIL | N/A
Typing: PASS | FAIL
Tests: PASS | FAIL
Duplication: PASS | FAIL
Naming: PASS | FAIL
Error Handling: PASS | FAIL
Concurrency/Idempotency: PASS | FAIL | N/A
Observability: PASS | FAIL
Maintainability: PASS | FAIL

Findings:
BLOCKER: <count>
HIGH: <count>
MEDIUM: <count>
LOW: <count>
INFO: <count>

Ready to commit: YES | NO
```

If `Ready to commit: NO`, explain exactly what must be fixed.

---

# 20. Stop Conditions

Do not approve the quality gate if any of these remain:

- BLOCKER finding,
- unresolved HIGH finding,
- failing required tests,
- failing required type checks,
- failing required lint checks,
- broken architecture boundary,
- known cross-tenant data risk,
- known insecure secret handling,
- known destructive retry risk,
- knowingly broken public contract.

---

# 21. Anti-Patterns

Do not:

- rewrite unrelated code "while here,"
- refactor stable code without reason,
- introduce abstractions solely to remove two similar lines,
- create generic `utils` dumping grounds,
- silence type errors instead of fixing them,
- suppress linter rules without explanation,
- hide errors behind broad exception handling,
- replace explicit domain names with generic names,
- use comments to excuse bad structure,
- introduce framework-specific infrastructure details into domain logic.

---

# 22. Review Philosophy

Prefer:
- explicit over clever,
- boring over magical,
- typed over ambiguous,
- cohesive over generic,
- deterministic authorization over model judgment,
- small composable services over god objects,
- bounded workflows over open-ended loops,
- testable contracts over hidden coupling,
- ports/adapters where infrastructure portability matters,
- measurable quality over stylistic preference.

The goal is not theoretical perfection.

The goal is a codebase another senior engineer can safely understand, modify, test, deploy, and operate.
