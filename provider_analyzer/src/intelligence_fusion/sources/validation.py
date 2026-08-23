from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any

from .common import date_iso, norm_text

_MIN_EVENT_DATE = date(2007, 1, 1)
_ORDER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{3,63}$")


def valid_chilean_rut(value: Any) -> str | None:
    """Return a normalized RUT only when syntax and check digit are valid."""
    raw = re.sub(r"[^0-9Kk]", "", str(value or "")).upper()
    if len(raw) < 7 or len(raw) > 9:
        return None
    body, supplied = raw[:-1], raw[-1]
    if not body.isdigit():
        return None
    total = 0
    multiplier = 2
    for digit in reversed(body):
        total += int(digit) * multiplier
        multiplier = 2 if multiplier == 7 else multiplier + 1
    check = 11 - (total % 11)
    expected = "0" if check == 11 else "K" if check == 10 else str(check)
    if supplied != expected:
        return None
    return f"{body}-{supplied}"


def stable_party_id(rut: Any, name: Any) -> tuple[str | None, str | None]:
    rut_id = valid_chilean_rut(rut)
    if rut_id:
        return rut_id, "RUT"
    label = norm_text(name)
    if len(label) >= 3 and any(ch.isalpha() for ch in label):
        return label, "NAME"
    return None, None


def valid_order_id(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(_ORDER_ID_RE.fullmatch(text) and "-" in text and any(ch.isdigit() for ch in text))


def plausible_event_date(value: Any, *, max_date: date | None = None) -> str:
    parsed = date_iso(value)
    if not parsed:
        return ""
    d = date.fromisoformat(parsed)
    ceiling = max_date or datetime.now(timezone.utc).date()
    if d < _MIN_EVENT_DATE or d > ceiling:
        return ""
    return parsed
