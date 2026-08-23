from __future__ import annotations

import importlib.util
from pathlib import Path

from intelligence_fusion.sources.validation import plausible_event_date, stable_party_id, valid_chilean_rut, valid_order_id


def load_persist_module():
    path = Path(__file__).parents[1] / 'scripts' / 'persist_provider_month.py'
    spec = importlib.util.spec_from_file_location('persist_provider_month', path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_rut_validation_rejects_shifted_short_values():
    assert valid_chilean_rut('CR 189') is None
    assert stable_party_id('CL', 'CL') == (None, None)


def test_order_id_rejects_descriptive_shifted_text():
    assert valid_order_id('1234-56-SE24')
    assert not valid_order_id('Proveniente de licitación pública')


def test_event_date_rejects_impossible_historical_value():
    assert plausible_event_date('1379-09-10') == ''
    assert plausible_event_date('2024-03-04') == '2024-03-04'


def test_route_partition_is_derived_from_event_date_not_source_month():
    mod = load_persist_module()
    event, reason = mod.normalize_route_event({'date':'2024-03-04','buyer_id':'61111111-1','supplier_id':'76222222-2','pair_id':'76222222-2::61111111-1','product_key':'CODE:43211902','status':'PURCHASED','order_id':'1234-56-SE24','source':'MERCADO_PUBLICO_BULK_ORDERS'},source_year=2024,source_month=1,now='2026-08-23T16:00:00+00:00')
    assert reason is None
    assert event['year'] == 2024 and event['month'] == 3
    assert event['source_year'] == 2024 and event['source_month'] == 1


def test_route_event_quarantines_impossible_date():
    mod = load_persist_module()
    event, reason = mod.normalize_route_event({'date':'1379-09-10','buyer_id':'CL','product_key':'TEXT:bad row','status':'PURCHASED','order_id':'Proveniente de licitación pública'},source_year=2024,source_month=1,now='2026-08-23T16:00:00+00:00')
    assert event is None
    assert reason == 'INVALID_EVENT_DATE'
