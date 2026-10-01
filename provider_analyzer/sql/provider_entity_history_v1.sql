-- Provider Analyzer · consulta histórica compacta por RUT
-- Mantiene el warehouse pesado en AML CLAUDE y expone sólo un contrato acotado.

create or replace function public.provider_entity_history_v1(
  p_rut text,
  p_from_year integer default 2020,
  p_to_year integer default extract(year from current_date)::integer
)
returns jsonb
language plpgsql
security definer
set search_path = public, provider_analyzer, pg_temp
as $$
declare
  v_rut text := upper(regexp_replace(coalesce(p_rut,''),'[^0-9Kk]','','g'));
  v_from integer := greatest(2007, least(coalesce(p_from_year,2020), extract(year from current_date)::integer));
  v_to integer;
  v_result jsonb;
begin
  if v_rut !~ '^[0-9]{6,8}[0-9K]$' then
    raise exception 'INVALID_RUT' using errcode='22023';
  end if;

  v_to := greatest(v_from, least(coalesce(p_to_year, extract(year from current_date)::integer), extract(year from current_date)::integer));

  with sy as materialized (
    select year,supplier_id,amount_total_clp,order_count,buyer_count,active_months,first_seen,last_seen,buyers
    from provider_analyzer.supplier_year
    where upper(regexp_replace(supplier_id,'[^0-9Kk]','','g')) = v_rut
      and year between v_from and v_to
  ), buyer_expanded as materialized (
    select
      b.value->>0 as buyer_id,
      coalesce((b.value->>1)::numeric,0) as amount_clp,
      coalesce((b.value->>2)::bigint,0) as order_count
    from sy
    cross join lateral jsonb_array_elements(coalesce(sy.buyers,'[]'::jsonb)) b(value)
    where jsonb_typeof(b.value)='array' and jsonb_array_length(b.value)>=3
  ), buyer_agg as (
    select buyer_id,sum(amount_clp) amount_clp,sum(order_count) order_count
    from buyer_expanded
    where coalesce(buyer_id,'')<>''
    group by buyer_id
  ), summary as (
    select
      min(year)::integer first_year,
      max(year)::integer last_year,
      min(first_seen) first_seen,
      max(last_seen) last_seen,
      coalesce(sum(amount_total_clp),0) amount_clp,
      coalesce(sum(order_count),0)::bigint order_count,
      (select count(*)::integer from buyer_agg) buyer_count
    from sy
  ), supplier_identity as (
    select i.canonical_label
    from provider_analyzer.party_identity i
    where i.party_key=v_rut
    limit 1
  )
  select jsonb_build_object(
    'ok',true,
    'schema','PROVIDER_ENTITY_HISTORY_V1',
    'rut',v_rut,
    'label',(select canonical_label from supplier_identity),
    'period',jsonb_build_object('from_year',v_from,'to_year',v_to),
    'summary',case when exists(select 1 from sy)
      then ((select to_jsonb(summary) from summary) || jsonb_build_object('label',(select canonical_label from supplier_identity)))
      else null end,
    'years',coalesce((select jsonb_agg(to_jsonb(x) order by x.year desc) from (
      select year,amount_total_clp amount_clp,order_count,buyer_count,active_months,first_seen,last_seen from sy
    ) x),'[]'::jsonb),
    'buyers',coalesce((select jsonb_agg(to_jsonb(x) order by x.amount_clp desc nulls last,x.buyer_id) from (
      select a.buyer_id,i.canonical_label buyer_label,a.amount_clp,a.order_count
      from buyer_agg a
      left join provider_analyzer.party_identity i
        on i.party_key=upper(regexp_replace(a.buyer_id,'[^0-9A-Za-z]','','g'))
      order by a.amount_clp desc nulls last,a.buyer_id
      limit 100
    ) x),'[]'::jsonb),
    'semantics',jsonb_build_object(
      'source','ChileCompra · provider_analyzer.supplier_year',
      'identity_source','ChileCompra · provider_analyzer.party_identity',
      'amounts','Montos agregados por proveedor y año.',
      'buyers','Compradores agregados a partir del arreglo anual buyers; máximo 100 contrapartes por respuesta.',
      'public_data',true
    )
  ) into v_result;

  return v_result;
end
$$;

revoke all on function public.provider_entity_history_v1(text,integer,integer) from public,anon,authenticated;
grant execute on function public.provider_entity_history_v1(text,integer,integer) to service_role;
comment on function public.provider_entity_history_v1(text,integer,integer) is 'Consulta histórica compacta de Mercado Público por un RUT y período. Sólo service_role; usada por Edge Function acotada.';
