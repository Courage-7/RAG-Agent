begin;

select plan(8);

select has_table(
  'public',
  'ingestion_jobs',
  'ingestion_jobs exists in the public application schema'
);

select has_table(
  'private',
  'job_dispatch_outbox',
  'job_dispatch_outbox exists in the private schema'
);

select is(
  (select relrowsecurity from pg_class where oid = 'public.ingestion_jobs'::regclass),
  true,
  'ingestion_jobs has RLS enabled'
);

select is(
  (select relrowsecurity from pg_class where oid = 'private.job_dispatch_outbox'::regclass),
  true,
  'job_dispatch_outbox has RLS enabled'
);

select ok(
  not has_table_privilege('anon', 'public.ingestion_jobs', 'select'),
  'anon cannot read ingestion jobs'
);

select ok(
  not has_table_privilege('authenticated', 'public.ingestion_jobs', 'select'),
  'authenticated users cannot read jobs before tenant policies exist'
);

select ok(
  not has_table_privilege('anon', 'public.ingestion_jobs', 'insert'),
  'anon cannot create ingestion jobs'
);

select ok(
  not has_table_privilege('authenticated', 'private.job_dispatch_outbox', 'select'),
  'authenticated users cannot read the private dispatch outbox'
);

select * from finish();
rollback;

