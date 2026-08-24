from __future__ import annotations


def compact_source_context(signal: dict) -> dict:
    """Keep source identifiers needed for review without duplicating reason/metrics."""
    out = {}
    for key in ('tender_id', 'buyer_name', 'scope'):
        value = signal.get(key)
        if value not in (None, ''):
            out[key] = value
    evidence_ids = signal.get('evidence_ids') or []
    if evidence_ids:
        out['source_evidence_ids'] = evidence_ids
    return out


def compact_priority_context(priority: dict) -> dict:
    """Remove duplicated history while preserving every field used to explain priority."""
    keys = (
        'review_key',
        'review_priority',
        'tier',
        'signal_types',
        'signal_count',
        'comparability_index_median',
        'alternative_route_count',
        'components',
        'history_context',
        'history_used_for_priority',
        'history_context_guardrail',
    )
    return {key: priority.get(key) for key in keys if key in priority}
