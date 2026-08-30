# ADR-002: Supabase as the persistent platform

- Status: Accepted
- Date: 2026-08-29

## Context

The product needs Postgres, vector and lexical search, authentication, object storage, row-level authorization, and recoverable state without operating several unrelated data systems.

## Decision

Use Supabase Postgres as the system of record, Supabase Auth for email OTP/magic-link identity, private Storage buckets for source artifacts, and Postgres vector/full-text facilities for retrieval. All exposed tables use RLS and least-privilege grants. Browser, API, worker, and migration credentials remain distinct. Service-role credentials never reach a browser.

## Consequences

Tenant isolation can be enforced at the data boundary and tested with pgTAP. Supabase becomes a material platform dependency, so migrations remain plain SQL and domain code depends on ports rather than Supabase client types.
