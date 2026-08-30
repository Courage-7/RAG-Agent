create schema if not exists private;

revoke all on schema private from public, anon, authenticated;

create type public.job_operation as enum (
  'document_ingestion',
  'embedding_batch',
  'maintenance'
);

create type public.job_status as enum (
  'queued',
  'running',
  'retry_scheduled',
  'completed',
  'failed',
  'cancelled',
  'dead_letter'
);

create type public.ingestion_stage as enum (
  'queued',
  'validating',
  'parsing',
  'normalizing',
  'chunking',
  'enriching',
  'embedding',
  'indexing',
  'verifying',
  'completed'
);

create table public.ingestion_jobs (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null,
  document_version_id uuid not null,
  operation public.job_operation not null default 'document_ingestion',
  status public.job_status not null default 'queued',
  current_stage public.ingestion_stage not null default 'queued',
  attempt_count integer not null default 0 check (attempt_count >= 0),
  max_attempts integer not null default 3 check (max_attempts > 0),
  idempotency_key text not null check (length(idempotency_key) between 8 and 200),
  pipeline_version text not null check (length(pipeline_version) between 1 and 100),
  payload_schema_version smallint not null default 1 check (payload_schema_version = 1),
  worker_id text,
  lease_expires_at timestamptz,
  heartbeat_at timestamptz,
  available_at timestamptz not null default now(),
  cancel_requested_at timestamptz,
  cancel_requested_by uuid,
  cancellation_reason text,
  failure_code text,
  failure_message text,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  updated_at timestamptz not null default now(),
  completed_at timestamptz,
  failed_at timestamptz,
  constraint ingestion_jobs_workspace_idempotency_key unique (workspace_id, idempotency_key),
  constraint ingestion_jobs_attempt_limit check (attempt_count <= max_attempts),
  constraint ingestion_jobs_lease_pair check (
    (lease_expires_at is null and worker_id is null)
    or (lease_expires_at is not null and worker_id is not null)
  ),
  constraint ingestion_jobs_terminal_timestamps check (
    (status = 'completed' and completed_at is not null and failed_at is null)
    or (status in ('failed', 'dead_letter') and failed_at is not null and completed_at is null)
    or (status not in ('completed', 'failed', 'dead_letter') and completed_at is null and failed_at is null)
  )
);

comment on table public.ingestion_jobs is
  'Authoritative durable state for ingestion and maintenance operations; Redis is transport only.';
comment on column public.ingestion_jobs.failure_message is
  'Sanitized diagnostic summary. Provider payloads, secrets, and document contents are forbidden.';

create index ingestion_jobs_runnable_idx
  on public.ingestion_jobs (available_at, created_at)
  where status in ('queued', 'retry_scheduled');

create index ingestion_jobs_expired_lease_idx
  on public.ingestion_jobs (lease_expires_at)
  where status = 'running';

create index ingestion_jobs_document_version_idx
  on public.ingestion_jobs (document_version_id, created_at desc);

alter table public.ingestion_jobs enable row level security;
revoke all on table public.ingestion_jobs from anon, authenticated;

create table private.job_dispatch_outbox (
  id bigint generated always as identity primary key,
  event_id uuid not null default gen_random_uuid() unique,
  job_id uuid not null references public.ingestion_jobs (id) on delete cascade,
  operation public.job_operation not null,
  payload jsonb not null check (jsonb_typeof(payload) = 'object'),
  attempt_count integer not null default 0 check (attempt_count >= 0),
  max_attempts integer not null default 20 check (max_attempts > 0),
  available_at timestamptz not null default now(),
  claimed_at timestamptz,
  claimed_by text,
  dispatched_at timestamptz,
  transport_message_id text,
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint job_dispatch_outbox_job_operation unique (job_id, operation),
  constraint job_dispatch_outbox_attempt_limit check (attempt_count <= max_attempts),
  constraint job_dispatch_outbox_claim_pair check (
    (claimed_at is null and claimed_by is null)
    or (claimed_at is not null and claimed_by is not null)
  )
);

comment on table private.job_dispatch_outbox is
  'Transactional dispatch intent replayed to the transient Redis/Dramatiq broker.';
comment on column private.job_dispatch_outbox.payload is
  'Identifier-only transport envelope. Large artifacts, document text, credentials, and authorization state are forbidden.';

create index job_dispatch_outbox_pending_idx
  on private.job_dispatch_outbox (available_at, id)
  where dispatched_at is null;

alter table private.job_dispatch_outbox enable row level security;
revoke all on table private.job_dispatch_outbox from public, anon, authenticated;

create function private.set_updated_at()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

revoke all on function private.set_updated_at() from public, anon, authenticated;

create trigger ingestion_jobs_set_updated_at
before update on public.ingestion_jobs
for each row execute function private.set_updated_at();

create trigger job_dispatch_outbox_set_updated_at
before update on private.job_dispatch_outbox
for each row execute function private.set_updated_at();
