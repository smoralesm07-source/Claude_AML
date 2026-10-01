-- Provider Analyzer · compact Mercado Publico identity directory.
-- Stores only party identity, never raw purchase-order rows.

create table if not exists provider_analyzer.party_identity (
  party_key text primary key,
  party_id text not null,
  canonical_label text not null,
  roles text[] not null default '{}'::text[],
  first_seen date,
  last_seen date,
  source text not null default 'CHILECOMPRA_OC_DA',
  source_year smallint,
  source_month smallint,
  updated_at timestamptz not null default now()
);

create index if not exists party_identity_label_idx
  on provider_analyzer.party_identity (lower(canonical_label));

create index if not exists ps_supplier_metric_identity_key_idx
  on public.ps_supplier_metric ((regexp_replace(upper(supplier_id),'[^0-9K]','','g')));
create index if not exists ps_buyer_metric_identity_key_idx
  on public.ps_buyer_metric ((regexp_replace(upper(buyer_id),'[^0-9K]','','g')));
create index if not exists ps_supplier_metric_top_buyer_key_idx
  on public.ps_supplier_metric ((regexp_replace(upper(top_buyer_id),'[^0-9K]','','g')));

create or replace function public.provider_identity_ingest_v1(p_rows jsonb)
returns jsonb
language plpgsql
security definer
set search_path = public, provider_analyzer, pg_temp
as $$
declare
  v_received integer := jsonb_array_length(coalesce(p_rows,'[]'::jsonb));
  v_written integer := 0;
begin
  if v_received < 1 or v_received > 1000 then
    raise exception 'INVALID_BATCH' using errcode='22023';
  end if;

  with incoming as (
    select
      nullif(trim(x.party_id),'') party_id,
      upper(regexp_replace(coalesce(x.party_id,''),'[^0-9A-Za-z]','','g')) party_key,
      nullif(trim(x.canonical_label),'') canonical_label,
      coalesce(x.roles,'{}'::text[]) roles,
      x.first_seen,
      x.last_seen,
      coalesce(nullif(trim(x.source),''),'CHILECOMPRA_OC_DA') source,
      x.source_year,
      x.source_month
    from jsonb_to_recordset(p_rows) as x(
      party_id text, canonical_label text, roles text[], first_seen date, last_seen date,
      source text, source_year int, source_month int
    )
  ), valid as (
    select * from incoming
    where party_id is not null and party_key <> '' and canonical_label is not null
      and source_year between 2007 and extract(year from current_date)::int
      and source_month between 1 and 12
  ), upserted as (
    insert into provider_analyzer.party_identity(
      party_key,party_id,canonical_label,roles,first_seen,last_seen,source,source_year,source_month,updated_at
    )
    select party_key,party_id,canonical_label,roles,first_seen,last_seen,source,source_year::smallint,source_month::smallint,now()
    from valid
    on conflict (party_key) do update set
      party_id = case
        when (excluded.source_year::int*12+excluded.source_month::int) >= (coalesce(provider_analyzer.party_identity.source_year,0)::int*12+coalesce(provider_analyzer.party_identity.source_month,0)::int)
          then excluded.party_id else provider_analyzer.party_identity.party_id end,
      canonical_label = case
        when (excluded.source_year::int*12+excluded.source_month::int) >= (coalesce(provider_analyzer.party_identity.source_year,0)::int*12+coalesce(provider_analyzer.party_identity.source_month,0)::int)
          then excluded.canonical_label else provider_analyzer.party_identity.canonical_label end,
      roles = array(select distinct r from unnest(coalesce(provider_analyzer.party_identity.roles,'{}'::text[]) || coalesce(excluded.roles,'{}'::text[])) r order by r),
      first_seen = case when provider_analyzer.party_identity.first_seen is null then excluded.first_seen when excluded.first_seen is null then provider_analyzer.party_identity.first_seen else least(provider_analyzer.party_identity.first_seen,excluded.first_seen) end,
      last_seen = case when provider_analyzer.party_identity.last_seen is null then excluded.last_seen when excluded.last_seen is null then provider_analyzer.party_identity.last_seen else greatest(provider_analyzer.party_identity.last_seen,excluded.last_seen) end,
      source = case
        when (excluded.source_year::int*12+excluded.source_month::int) >= (coalesce(provider_analyzer.party_identity.source_year,0)::int*12+coalesce(provider_analyzer.party_identity.source_month,0)::int)
          then excluded.source else provider_analyzer.party_identity.source end,
      source_year = greatest(coalesce(provider_analyzer.party_identity.source_year,0),excluded.source_year),
      source_month = case
        when excluded.source_year > coalesce(provider_analyzer.party_identity.source_year,0) then excluded.source_month
        when excluded.source_year = coalesce(provider_analyzer.party_identity.source_year,0) then greatest(coalesce(provider_analyzer.party_identity.source_month,0),excluded.source_month)
        else provider_analyzer.party_identity.source_month end,
      updated_at = now()
    returning party_key
  ) select count(*) into v_written from upserted;

  update public.ps_supplier_metric s
  set supplier_label = i.canonical_label
  from provider_analyzer.party_identity i
  where regexp_replace(upper(s.supplier_id),'[^0-9K]','','g') = i.party_key
    and 'supplier'=any(i.roles)
    and nullif(trim(s.supplier_label),'') is null;

  update public.ps_buyer_metric b
  set buyer_label = i.canonical_label
  from provider_analyzer.party_identity i
  where regexp_replace(upper(b.buyer_id),'[^0-9K]','','g') = i.party_key
    and 'buyer'=any(i.roles)
    and nullif(trim(b.buyer_label),'') is null;

  update public.ps_supplier_metric s
  set top_buyer_label = i.canonical_label
  from provider_analyzer.party_identity i
  where regexp_replace(upper(coalesce(s.top_buyer_id,'')),'[^0-9K]','','g') = i.party_key
    and 'buyer'=any(i.roles)
    and nullif(trim(s.top_buyer_label),'') is null;

  return jsonb_build_object('ok',true,'received',v_received,'written',v_written,'storage','PARTY_IDENTITY_V1');
end
$$;

revoke all on function public.provider_identity_ingest_v1(jsonb) from public,anon,authenticated;
grant execute on function public.provider_identity_ingest_v1(jsonb) to service_role;
