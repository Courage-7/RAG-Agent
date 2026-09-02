# Credentials and service configuration
Updated: 2026-08-29 

This is the single inventory of values that the project may need from you. It intentionally contains names and setup links only, never paste a real key, password, token, connection string, or OAuth client secret into this document, a notebook, source code, an issue, or chat history.

## Where values belong

| Environment | Store values in | Never store there |
| --- | --- | --- |
| Local development | Untracked root `.env`, copied from `.env.example` | Production secrets or another developer's keys |
| GitHub Actions | Repository or protected Environment secrets | Application runtime secrets that CI does not use |
| FastAPI Cloud API | Application environment/secrets | Browser-exposed build variables |
| Worker host | That host's secret manager | Frontend configuration |
| Supabase hosted services | Supabase Dashboard settings or Vault, depending on the feature | Tracked SQL, unless the value is deliberately public and non-sensitive |
| Browser/frontend | Public URL and Supabase publishable key only | Groq, Composio, Supabase secret/service-role, database, SMTP, or deployment credentials |

Use distinct credentials for local, staging, and production. Prefer one scoped key per service so it can be revoked independently. Rotate immediately after suspected exposure and on a scheduled basis in production.

## Required now

These variables are already read by the foundation code.

### Application

| Variable | Secret? | Local default | Purpose |
| --- | --- | --- | --- |
| `RAG_ENVIRONMENT` | No | `local` | One of `local`, `test`, `staging`, or `production`. |
| `RAG_LOG_LEVEL` | No | `INFO` | Application log threshold. |
| `RAG_JSON_LOGS` | No | `false` | Use `true` in hosted environments for structured JSON logs. |

### Groq

| Variable | Secret? | Required | Purpose/source |
| --- | --- | --- | --- |
| `GROQ_API_KEY` | Yes, server-only | Live inference | Create a project-specific key in the [Groq API Keys console](https://console.groq.com/keys). Never expose it in browser code. |
| `RAG_GROQ_FAST_MODEL` | No | Yes | Strict structured routing/grading model; current candidate is `openai/gpt-oss-20b`. |
| `RAG_GROQ_QUALITY_MODEL` | No | Yes | High-quality synthesis model; current candidate is `openai/gpt-oss-120b`. |
| `RAG_GROQ_AGENT_MODEL` | No | Yes | Bounded tool-calling model; current candidate is `openai/gpt-oss-120b`. |

The model mappings are candidates until the evaluation suite records schema validity, quality, latency, token usage, and rate-limit behavior. Create separate Groq projects/keys and spending limits for development, staging, and production. Review [Groq security onboarding](https://console.groq.com/docs/production-readiness/security-onboarding) and [project limits](https://console.groq.com/docs/projects) before production.

### Supabase and PostgreSQL

| Variable | Secret? | Local default | Purpose/source |
| --- | --- | --- | --- |
| `RAG_SUPABASE_URL` | No | `http://127.0.0.1:54321` | Hosted value is the project URL from the Supabase **Connect** dialog. |
| `RAG_SUPABASE_PUBLISHABLE_KEY` | Public but environment-specific | Local CLI output | Low-privilege key for Auth/browser clients. Prefer `sb_publishable_...`, not a new legacy `anon` key. RLS remains mandatory. |
| `RAG_DATABASE_URL` | Yes outside local development | Local Postgres URL | Server/worker migration or direct database connection. Obtain the correct direct or pooler URL from **Connect** and preserve its SSL requirements. |

Get hosted keys from Supabase **Project Settings → API Keys**. New projects should use independently rotatable publishable and secret keys; the [Supabase key migration guide](https://supabase.com/docs/guides/getting-started/migrating-to-new-api-keys) explains the boundary. A publishable key is safe to distribute but does not replace RLS. Database URLs contain a password and are always secrets.

### Redis/Dramatiq

| Variable | Secret? | Local default | Purpose |
| --- | --- | --- | --- |
| `RAG_REDIS_BROKER_URL` | Yes when it contains credentials | `redis://127.0.0.1:6379/0` | Dramatiq broker connection. Production must use a private managed endpoint, authentication, TLS, persistence, and the validated HA/RPO/RTO tier. |

Do not share the production broker with an eviction-based cache. Redis is transport only; PostgreSQL remains authoritative.

## Required for authentication and document storage

These arrive in Milestone 2 and should not be supplied until the implementation consumes them.

| Configuration | Secret? | Where to configure |
| --- | --- | --- |
| Public application URL | No | Supabase Auth URL Configuration and future `RAG_PUBLIC_APP_URL`. |
| Allowed Auth redirect URLs | No | Supabase Auth URL Configuration; set exact local, staging, and production callback URLs. |
| Email OTP versus magic-link template | No | Supabase Auth email templates. The product decision is still open. |
| Custom SMTP host, port, username, password, sender | Yes except host/port | Configure in Supabase Auth SMTP settings, not in this application's `.env`, unless self-hosting. Production must use a deliverability-capable custom SMTP provider. |
| Private `documents` bucket | No key | Created by `supabase/config.toml`; hosted policies and MIME/size limits are applied through migrations/configuration. |
| `RAG_SUPABASE_SECRET_KEY` | Yes, server-only | Planned worker/admin client key. Prefer a scoped `sb_secret_...` key from Supabase API Keys. It bypasses RLS and must never reach a browser. |

The legacy `service_role` key should be treated with the same severity as a database administrator credential. Do not provide it if a new scoped secret key can serve the backend use case.

## Required for Composio connectors

These arrive in the bounded-agent milestone.

| Variable/configuration | Secret? | Purpose/source |
| --- | --- | --- |
| `COMPOSIO_API_KEY` | Yes, server-only | Prefer a scoped project key from Composio **Settings → Project Settings → API Keys**. See [Composio authentication](https://docs.composio.dev/reference/v3/authentication). |
| `COMPOSIO_GOOGLE_AUTH_CONFIG_ID` | No, but internal | ID of the enabled Google OAuth auth config used for Calendar/Gmail/Drive connections. |
| OAuth client ID and client secret | Secret only for the client secret | Needed only if we choose custom OAuth instead of Composio managed auth; store in Composio, not in browser code. |
| OAuth redirect/callback URLs | No | Copy exactly from the Composio auth-config setup into the Google Cloud OAuth application. |
| Webhook signing secret | Yes | Add only if the selected Composio lifecycle uses webhooks; verify every signature server-side. |

Composio sessions must use the application's stable internal user UUID. Store returned session, connected-account, and auth-config identifiers in PostgreSQL; never store provider access or refresh tokens. Start with read-only Calendar/web actions. Every write remains subject to the application's approval and idempotency contracts, even though Composio executes it. See the [Composio LangChain/LangGraph provider guide](https://docs.composio.dev/docs/providers/langchain) and [auth-config reference](https://docs.composio.dev/reference/api-reference/auth-configs).

## Web search provider — selection pending

Choose one provider after relevance, freshness, citation, latency, privacy, and cost evaluation. Do not provide both keys unless both adapters are intentionally implemented.

| Variable | Secret? | Use when selected |
| --- | --- | --- |
| `WEB_SEARCH_PROVIDER` | No | Suggested values: `tavily` or `exa`; no default is committed yet. |
| `TAVILY_API_KEY` | Yes, server-only | Only for a Tavily adapter or Composio Tavily connected account. |
| `EXA_API_KEY` | Yes, server-only | Only for an Exa adapter or Composio Exa connected account. |

The application must record result URLs, titles, retrieval time, and provider metadata for citations. Retrieved web content is untrusted input and cannot grant tool permission.

## Observability

LangSmith remains optional until data controls and redaction are approved.

| Variable | Secret? | Purpose |
| --- | --- | --- |
| `LANGSMITH_TRACING` | No | `false` by default; enable deliberately per environment. |
| `LANGSMITH_API_KEY` | Yes, server-only | LangSmith project/workspace API key. |
| `LANGSMITH_PROJECT` | No | Suggested names: `rag-agent-local`, `rag-agent-staging`, `rag-agent-production`. |
| `LANGSMITH_ENDPOINT` | No | Region-specific LangSmith API endpoint. |
| `LANGSMITH_WORKSPACE_ID` | Internal identifier | Required when a key can access multiple workspaces. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | No or internal | OpenTelemetry collector endpoint. |
| `OTEL_EXPORTER_OTLP_HEADERS` | Usually yes | Authentication headers for the collector. |

LangSmith documents the current tracing variables and regional endpoints in its [LangChain tracing guide](https://docs.langchain.com/langsmith/trace-with-langchain). Before enabling production traces, approve redaction, sampling, retention, residency, and whether prompts/retrieved text may leave the application boundary.

## FastAPI Cloud and GitHub deployment

These belong in protected GitHub Environment secrets, not `.env.example` or application logs.

| GitHub secret | Secret? | Purpose/source |
| --- | --- | --- |
| `FASTAPI_CLOUD_TOKEN` | Yes | Expiring deploy token created for CI. |
| `FASTAPI_CLOUD_APP_ID` | Internal identifier | Exact FastAPI Cloud application UUID. |

Current FastAPI Cloud documentation uses these names for [deploy tokens](https://fastapicloud.com/docs/advanced-features/deploy-tokens/). Protect production with required approval and deployment concurrency. The API may run there only after the hosting spike; the heavy Dramatiq worker requires its own validated runtime and secrets.

## Embeddings, reranking, parsing, and malware scanning — decisions pending

Do not purchase or provide credentials yet. The evaluation milestone must select:

- embedding provider, model, dimension, batch limits, and data-retention terms;
- reranker provider/model or an acceptable local model;
- Docling deployment mode and any remote service authentication;
- malware scanner and upload/decompression limits.

When selected, add one provider-neutral profile plus the minimum server-only credential. Do not put model names directly into graph nodes or maintain several production indexes without an evaluation-backed reason.

## Copy-to-`.env` checklist

Start with the tracked `.env.example`:

```bash
cp .env.example .env
```

For today's credential-free tests, no value is required. For a live Groq smoke test, provide only:

```dotenv
GROQ_API_KEY=<development-project-key>
```

For hosted Supabase development later, add:

```dotenv
RAG_SUPABASE_URL=https://<project-ref>.supabase.co
RAG_SUPABASE_PUBLISHABLE_KEY=sb_publishable_<redacted>
RAG_DATABASE_URL=postgresql://<redacted>
```

Never copy the example placeholders back into this Markdown file. Validate configuration by checking presence and service connectivity without printing complete secret values.

## Provisioning checklist

- [ ] Create separate development, staging, and production Groq projects/keys and budgets.
- [ ] Create Supabase projects/branches and record project URLs plus publishable keys.
- [ ] Select OTP or magic-link UX, exact redirect URLs, custom SMTP provider, and recovery flow.
- [ ] Create separate scoped Supabase backend keys only when worker/admin operations require them.
- [ ] Select a private managed Redis deployment and validate persistence/HA.
- [ ] Create a scoped Composio project key and least-privilege Google auth config.
- [ ] Select and benchmark one web search provider.
- [ ] Decide LangSmith/OTel data controls before enabling production tracing.
- [ ] Create FastAPI Cloud staging/production applications and expiring deploy tokens.
- [ ] Record owner, creation date, scope, environment, expiry, and rotation date for every secret in the team's password/secret manager—not in Git.
