# Atomic Commits Skill

## Purpose

Ensure every code-changing task produces professional Git history.

A commit must represent one coherent semantic change that can be:

- understood independently,
- reviewed independently,
- reverted independently,
- cherry-picked independently,
- bisected meaningfully.

This skill runs only after the Code Quality Gate passes.

All commit messages must be:
- Conventional Commit compatible,
- single-line only,
- concise,
- descriptive,
- scoped when useful.

Never create multiline commit messages.

---

# 1. Required Commit Format

Use:

```text
<type>(<scope>): <description>
```

The scope may be omitted only when no meaningful scope exists.

Examples:

```text
feat(ingestion): add Redis-backed document job dispatch
fix(retrieval): preserve workspace filters during query rewrite
refactor(auth): centralize workspace authorization policy
test(queue): cover duplicate job delivery
docs(architecture): document worker queue boundaries
chore(deps): add Dramatiq Redis dependencies
ci(quality): run Ruff and Pyright on pull requests
perf(retrieval): batch lexical and vector candidate loading
build(worker): add Redis service to compose stack
```

---

# 2. Allowed Types

Use only:

```text
feat
fix
refactor
perf
test
docs
build
ci
chore
style
revert
```

Meaning:

## feat

New externally meaningful behavior or capability.

Example:

```text
feat(retrieval): add hybrid lexical and vector search
```

## fix

Corrects incorrect behavior.

Example:

```text
fix(auth): reject expired workspace memberships
```

## refactor

Changes internal structure without intended behavior change.

Example:

```text
refactor(queue): extract job queue port
```

## perf

Improves performance without changing intended behavior.

Example:

```text
perf(embeddings): batch chunk embedding requests
```

## test

Adds or changes tests only.

Example:

```text
test(ingestion): cover duplicate worker delivery
```

## docs

Documentation only.

Example:

```text
docs(architecture): document queue ownership boundaries
```

## build

Build system, packaging, runtime image, dependency/build configuration.

Example:

```text
build(worker): add Redis service to Docker Compose
```

## ci

CI/CD pipeline changes.

Example:

```text
ci(quality): enforce Ruff and Pyright checks
```

## chore

Maintenance that does not fit another type.

Example:

```text
chore(deps): update development dependencies
```

## style

Formatting-only change with no behavior change.

Use sparingly.

Example:

```text
style(api): apply Ruff formatting
```

## revert

Reverts a prior commit.

Example:

```text
revert(queue): remove Redis broker integration
```

---

# 3. Scope Rules

Scopes should describe a bounded module, feature, or subsystem.

Preferred examples:

```text
api
auth
ingestion
retrieval
reranking
embeddings
agents
tools
queue
worker
storage
database
observability
evals
security
ci
architecture
deps
```

Avoid meaningless scopes:

```text
backend
changes
update
misc
stuff
code
files
work
```

Prefer the narrowest useful stable scope.

Do not create a new scope for every filename.

---

# 4. Description Rules

Descriptions must:

- use imperative language,
- state the semantic change,
- remain concise,
- not end with a period,
- not contain ticket prose unless repository policy requires it,
- not explain implementation minutiae.

Good:

```text
fix(ingestion): prevent duplicate document activation
```

Bad:

```text
fix: fixed some stuff
```

Bad:

```text
feat(backend): updated multiple files
```

Bad:

```text
chore: changes
```

Bad:

```text
update code
```

---

# 5. Single-Line Rule

Every commit message must be one line.

Forbidden:

```text
feat(queue): add Redis queue integration

Adds queue abstraction.
Adds worker adapter.
Updates tests.
```

Required:

```text
feat(queue): add Redis-backed job dispatch
```

Do not add body text.

Do not add footer text.

Do not add generated descriptions.

Do not add Co-authored-by lines unless repository policy explicitly requires them.

---

# 6. Atomicity Definition

Atomic does not mean one file per commit.

Atomic means one semantic change per commit.

Examples:

A feature may require:

```text
queue.py
dramatiq_redis.py
ingestion_service.py
test_queue.py
```

If these files collectively implement one indivisible behavior, one commit can be correct:

```text
feat(ingestion): add Redis-backed asynchronous job dispatch
```

Conversely, one file may contain several unrelated changes and require splitting.

---

# 7. Atomicity Questions

Before staging, ask:

```text
Does this commit have one purpose?

Can I describe it clearly in one sentence?

Does it mix behavior and unrelated cleanup?

Does it mix refactoring and feature work?

Does it mix formatting with behavior?

Does it mix dependency changes with unrelated code?

Are tests included with the behavior they validate?

Can this commit be reverted without undoing unrelated work?

Can this commit be cherry-picked without unrelated changes?

Would git bisect point to a meaningful change?
```

If the answers reveal multiple purposes, split the commit.

---

# 8. Separate Refactoring from Behavior

Avoid:

```text
feat(retrieval): add query decomposition and reorganize retrieval package
```

Prefer:

```text
refactor(retrieval): reorganize retrieval strategy modules
```

then:

```text
feat(retrieval): add query decomposition strategy
```

Behavior changes should not be hidden inside large structural refactors.

---

# 9. Keep Tests With Behavior

When a test directly verifies new or fixed behavior, prefer committing it with the behavior.

Example:

```text
fix(ingestion): prevent duplicate document activation
```

may include:
- implementation fix,
- regression test.

A separate test commit is appropriate when:
- tests are added independently,
- tests cover already-existing behavior,
- test infrastructure itself is the change.

Do not split implementation and its essential regression test merely to increase commit count.

---

# 10. Dependency Changes

If a dependency is required solely for a feature and the repository remains valid only with both together, one commit may be appropriate.

Example:

```text
feat(worker): add Dramatiq Redis worker execution
```

If the dependency introduction is independently meaningful or preparatory:

```text
build(worker): add Redis and Dramatiq dependencies
```

then:

```text
feat(worker): implement Redis-backed Dramatiq broker
```

Use judgment.

Do not create artificially tiny commits that leave the repository broken.

---

# 11. Formatting Changes

Avoid mixing broad formatting with behavior.

Bad:

```text
feat(retrieval): add reranker and reformat entire package
```

Prefer:

```text
style(retrieval): apply formatter
```

then:

```text
feat(retrieval): add reranking stage
```

If formatting only touches lines already changed by the feature, it does not require a separate commit.

---

# 12. Documentation Changes

Documentation that is required to understand a feature may be included with the feature.

Large or independent documentation work should use:

```text
docs(<scope>): <description>
```

Example:

```text
docs(worker): document local Redis worker startup
```

---

# 13. Migration Changes

Database migrations should normally be committed with the behavior that requires them when the migration and feature are inseparable.

If the migration is intentionally preparatory and backward-compatible, it may be separate.

Example:

```text
feat(ingestion): add ingestion job lifecycle persistence
```

or:

```text
build(database): add ingestion job status columns
```

depending on project convention and intent.

Never split migrations in a way that leaves application code incompatible with the schema.

---

# 14. Commit Ordering

Order commits by dependency where practical.

Example:

```text
1. refactor(queue): extract job queue port
2. build(worker): add Redis and Dramatiq dependencies
3. feat(worker): implement Redis Dramatiq adapter
4. feat(ingestion): dispatch document jobs through queue port
5. docs(worker): document local background worker setup
```

Each commit should leave the repository buildable/testable where practical.

Do not intentionally create broken intermediate commits.

---

# 15. Diff Inspection Procedure

Before committing:

1. Run `git status`.
2. Inspect unstaged diff.
3. Inspect staged diff.
4. Identify semantic change groups.
5. Detect unrelated changes.
6. Detect formatting noise.
7. Detect generated files.
8. Detect secrets.
9. Detect accidental local configuration.
10. Map each semantic group to one commit message.
11. Stage only the files/hunks belonging to that group.
12. Re-check the staged diff.
13. Commit.
14. Repeat for remaining changes.

Never commit without inspecting the staged diff.

---

# 16. Partial Staging

Use partial/hunk staging when one file contains multiple semantic changes.

The agent should prefer:
- `git add -p`,
- equivalent IDE hunk staging,
- or temporary patch separation,

rather than forcing unrelated changes into one commit.

Do not modify user work simply to make staging easier.

---

# 17. User Work Protection

Never discard, reset, overwrite, or rewrite unrelated user changes merely to create a clean commit.

If unrelated changes already exist:

- identify them,
- leave them untouched,
- stage only relevant hunks/files.

Do not use destructive commands such as:

```text
git reset --hard
git checkout -- .
git clean -fd
```

unless the user explicitly requests them and their implications are understood.

---

# 18. Generated Files

Inspect generated files before committing.

Examples:

```text
lock files
database files
compiled assets
coverage output
logs
cache files
local environment files
temporary exports
```

Only commit generated files if repository policy requires them.

Never commit:

```text
.env
secrets
API keys
tokens
local credentials
```

---

# 19. Commit Message Selection

Choose the type based on the change's purpose, not the file type.

Changing a config file to enable a feature can still be:

```text
feat(...)
```

Changing source code purely to restructure it is:

```text
refactor(...)
```

Updating Docker Compose for build/runtime infrastructure is often:

```text
build(...)
```

Changing GitHub Actions is:

```text
ci(...)
```

---

# 20. Examples

## Good

```text
feat(auth): add email OTP session verification
fix(queue): prevent duplicate worker acknowledgement
refactor(retrieval): extract hybrid retrieval strategy
perf(embeddings): batch document chunk requests
test(auth): cover expired JWT rejection
docs(architecture): document multi-tenant retrieval boundaries
build(worker): add Redis service to compose stack
ci(quality): enforce Ruff Pyright and pytest
chore(deps): update Supabase client version
style(api): apply Ruff formatting
```

## Bad

```text
update stuff
backend changes
fix: bug fix
feat: new feature
chore: misc
refactor: cleanup
feat(rag): lots of improvements
fix(all): various fixes
```

---

# 21. Breaking Changes

If the repository adopts Conventional Commit breaking-change notation, use:

```text
feat(api)!: replace legacy document ingestion contract
```

Keep the message single-line.

Do not add a multiline `BREAKING CHANGE:` footer.

Only use `!` when the public contract is genuinely breaking.

---

# 22. Pre-Commit Validation

Before the first commit:

- Code Quality Gate must report `Ready to commit: YES`.
- Required tests must pass.
- Required lint/type checks must pass.
- No unresolved BLOCKER/HIGH quality findings may remain.

After splitting commits, verify that partitioning did not accidentally omit required tests or files.

---

# 23. Commit Execution Report

After creating commits, report:

```text
ATOMIC COMMIT REPORT

Commits created:
- <sha> <message>
- <sha> <message>

Uncommitted changes:
- <summary or "none">

Validation:
- quality gate: PASS
- tests: PASS
- lint: PASS
- types: PASS
```

Do not fabricate SHAs.

If the agent is only preparing messages and not actually committing, report:

```text
Proposed commits:
- <message>
- <message>
```

---

# 24. Stop Conditions

Do not commit if:

- Code Quality Gate failed,
- required tests fail,
- required lint/type checks fail,
- secret material is staged,
- unrelated user changes are staged,
- commit purpose cannot be described coherently,
- staged diff contains multiple unrelated semantic changes,
- repository would be intentionally broken after the commit.

---

# 25. History Quality Standard

The Git history should read like a technical changelog.

A reviewer should be able to scan:

```text
git log --oneline
```

and understand how the system evolved.

Prefer:

```text
refactor(queue): extract job queue port
build(worker): add Redis and Dramatiq dependencies
feat(worker): implement Redis-backed Dramatiq broker
feat(ingestion): dispatch document jobs through queue port
test(ingestion): cover duplicate worker delivery
```

over:

```text
update
more changes
fix
final fix
working now
cleanup
```

---

# 26. Final Rule

A commit is ready when it is:

- coherent,
- minimal without being artificially fragmented,
- independently understandable,
- safe to revert,
- validated,
- and named precisely.

Atomicity is semantic, not numerical.
