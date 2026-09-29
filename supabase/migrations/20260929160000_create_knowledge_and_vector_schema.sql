-- Migration: 20260929160000_create_knowledge_and_vector_schema.sql
-- Description: Core knowledge base, documents, versions, chunks, pgvector HNSW index, and hybrid search RPC.

create extension if not exists vector;

-- 1. Workspaces
create table if not exists public.workspaces (
  id uuid primary key default gen_random_uuid(),
  name text not null check (length(name) between 1 and 200),
  slug text not null check (length(slug) between 1 and 100) unique,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.workspaces enable row level security;
revoke all on table public.workspaces from anon, authenticated;

-- 2. Knowledge Bases
create table if not exists public.knowledge_bases (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  name text not null check (length(name) between 1 and 200),
  description text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint knowledge_bases_workspace_name unique (workspace_id, name)
);

create index if not exists knowledge_bases_workspace_idx
  on public.knowledge_bases(workspace_id);

alter table public.knowledge_bases enable row level security;
revoke all on table public.knowledge_bases from anon, authenticated;

-- 3. Documents
create table if not exists public.documents (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  knowledge_base_id uuid not null references public.knowledge_bases(id) on delete cascade,
  title text not null check (length(title) between 1 and 500),
  source_uri text,
  file_type text not null default 'text/plain',
  byte_size bigint not null default 0 check (byte_size >= 0),
  sha256 text not null check (length(sha256) = 64),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists documents_workspace_kb_idx
  on public.documents(workspace_id, knowledge_base_id);

alter table public.documents enable row level security;
revoke all on table public.documents from anon, authenticated;

-- 4. Document Versions
create table if not exists public.document_versions (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.documents(id) on delete cascade,
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  version_number integer not null default 1 check (version_number >= 1),
  status text not null default 'staged' check (status in ('staged', 'active', 'retired', 'failed')),
  raw_content text,
  chunk_count integer not null default 0 check (chunk_count >= 0),
  embedding_model text not null default 'BAAI/bge-small-en-v1.5',
  embedding_dimensions integer not null default 384 check (embedding_dimensions > 0),
  created_at timestamptz not null default now(),
  activated_at timestamptz,
  constraint document_versions_doc_ver unique (document_id, version_number)
);

create index if not exists document_versions_doc_status_idx
  on public.document_versions(document_id, status);

alter table public.document_versions enable row level security;
revoke all on table public.document_versions from anon, authenticated;

-- 5. Document Chunks (with lexical tsvector + dense pgvector)
create table if not exists public.document_chunks (
  id uuid primary key default gen_random_uuid(),
  document_version_id uuid not null references public.document_versions(id) on delete cascade,
  document_id uuid not null references public.documents(id) on delete cascade,
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  knowledge_base_id uuid not null references public.knowledge_bases(id) on delete cascade,
  chunk_index integer not null check (chunk_index >= 0),
  content text not null check (length(content) > 0),
  tsv_content tsvector generated always as (to_tsvector('english', content)) stored,
  embedding vector(384) not null,
  created_at timestamptz not null default now(),
  constraint document_chunks_version_index unique (document_version_id, chunk_index)
);

-- Lexical GIN Index
create index if not exists document_chunks_tsv_idx
  on public.document_chunks using gin(tsv_content);

-- Vector Cosine HNSW Index
create index if not exists document_chunks_embedding_hnsw_idx
  on public.document_chunks using hnsw (embedding vector_cosine_ops);

create index if not exists document_chunks_scope_idx
  on public.document_chunks (workspace_id, knowledge_base_id);

alter table public.document_chunks enable row level security;
revoke all on table public.document_chunks from anon, authenticated;

-- Updated at triggers
create trigger workspaces_set_updated_at
  before update on public.workspaces
  for each row execute function private.set_updated_at();

create trigger knowledge_bases_set_updated_at
  before update on public.knowledge_bases
  for each row execute function private.set_updated_at();

create trigger documents_set_updated_at
  before update on public.documents
  for each row execute function private.set_updated_at();

-- 6. Hybrid Search RPC (Dense + Lexical with Reciprocal Rank Fusion)
create or replace function public.match_chunks_hybrid(
  query_text text,
  query_embedding vector(384),
  match_count int,
  filter_workspace_id uuid,
  filter_knowledge_base_ids uuid[],
  rrf_k int default 60
)
returns table (
  chunk_id uuid,
  document_id uuid,
  document_version_id uuid,
  content text,
  source_label text,
  fused_score float,
  dense_score float,
  lexical_score float,
  rank int
)
language sql
security invoker
set search_path = ''
as $$
with dense_search as (
  select
    c.id as chunk_id,
    c.document_id,
    c.document_version_id,
    c.content,
    d.title as source_label,
    (1 - (c.embedding <=> query_embedding))::float as dense_score,
    row_number() over (order by c.embedding <=> query_embedding) as dense_rank
  from public.document_chunks c
  join public.documents d on d.id = c.document_id
  join public.document_versions v on v.id = c.document_version_id
  where c.workspace_id = filter_workspace_id
    and c.knowledge_base_id = any(filter_knowledge_base_ids)
    and v.status = 'active'
  order by c.embedding <=> query_embedding
  limit least(match_count * 2, 50)
),
lexical_search as (
  select
    c.id as chunk_id,
    c.document_id,
    c.document_version_id,
    c.content,
    d.title as source_label,
    ts_rank_cd(c.tsv_content, websearch_to_tsquery('english', query_text))::float as lexical_score,
    row_number() over (order by ts_rank_cd(c.tsv_content, websearch_to_tsquery('english', query_text)) desc) as lexical_rank
  from public.document_chunks c
  join public.documents d on d.id = c.document_id
  join public.document_versions v on v.id = c.document_version_id
  where c.workspace_id = filter_workspace_id
    and c.knowledge_base_id = any(filter_knowledge_base_ids)
    and v.status = 'active'
    and c.tsv_content @@ websearch_to_tsquery('english', query_text)
  order by lexical_score desc
  limit least(match_count * 2, 50)
),
fused as (
  select
    coalesce(d.chunk_id, l.chunk_id) as chunk_id,
    coalesce(d.document_id, l.document_id) as document_id,
    coalesce(d.document_version_id, l.document_version_id) as document_version_id,
    coalesce(d.content, l.content) as content,
    coalesce(d.source_label, l.source_label) as source_label,
    d.dense_score,
    l.lexical_score,
    (
      coalesce(1.0 / (rrf_k + d.dense_rank), 0.0) +
      coalesce(1.0 / (rrf_k + l.lexical_rank), 0.0)
    )::float as fused_score
  from dense_search d
  full outer join lexical_search l on d.chunk_id = l.chunk_id
)
select
  f.chunk_id,
  f.document_id,
  f.document_version_id,
  f.content,
  f.source_label,
  f.fused_score,
  f.dense_score,
  f.lexical_score,
  row_number() over (order by f.fused_score desc)::int as rank
from fused f
order by f.fused_score desc
limit match_count;
$$;
