from __future__ import annotations
import hashlib, json, re, unicodedata
from datetime import datetime, timezone
from typing import Any

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def clean_rut(value: Any) -> str | None:
    if value is None: return None
    s = re.sub(r"[^0-9Kk]", "", str(value)).upper()
    if len(s) < 2: return None
    return f"{s[:-1]}-{s[-1]}"

def norm_text(value: Any) -> str:
    s = unicodedata.normalize("NFKD", str(value or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).upper()
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def stable_hash(obj: Any) -> str:
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()

def event_id(prefix: str, *parts: Any) -> str:
    key = "|".join(str(x or "") for x in parts)
    return f"{prefix}-{hashlib.sha256(key.encode()).hexdigest()[:24]}"

def as_float(value: Any) -> float | None:
    try:
        if value in (None, ""): return None
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None

def date_iso(value: Any) -> str:
    """Normalize common ChileCompra date forms to YYYY-MM-DD; return empty string when unknown."""
    s = str(value or "").strip()
    if not s: return ""
    cleaned = s.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(cleaned).date().isoformat()
    except ValueError:
        pass
    head = s.split()[0].strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(head[:10], fmt).date().isoformat()
        except ValueError:
            pass
    return ""
