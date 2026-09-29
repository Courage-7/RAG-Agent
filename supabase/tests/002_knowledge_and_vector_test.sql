begin;

select plan(11);

select has_table(
  'public',
  'workspaces',
  'workspaces exists in public schema'
);

select has_table(
  'public',
  'knowledge_bases',
  'knowledge_bases exists in public schema'
);

select has_table(
  'public',
  'documents',
  'documents exists in public schema'
);

select has_table(
  'public',
  'document_versions',
  'document_versions exists in public schema'
);

select has_table(
  'public',
  'document_chunks',
  'document_chunks exists in public schema'
);

select is(
  (select relrowsecurity from pg_class where oid = 'public.workspaces'::regclass),
  true,
  'workspaces has RLS enabled'
);

select is(
  (select relrowsecurity from pg_class where oid = 'public.document_chunks'::regclass),
  true,
  'document_chunks has RLS enabled'
);

select ok(
  not has_table_privilege('anon', 'public.documents', 'select'),
  'anon cannot read documents'
);

select ok(
  not has_table_privilege('anon', 'public.document_chunks', 'select'),
  'anon cannot read document chunks'
);

select ok(
  not has_table_privilege('authenticated', 'public.document_chunks', 'insert'),
  'authenticated users cannot insert raw chunks directly'
);

select has_function(
  'public',
  'match_chunks_hybrid',
  ARRAY['text', 'vector', 'integer', 'uuid', 'uuid[]', 'integer'],
  'match_chunks_hybrid function exists'
);

select * from finish();
rollback;
