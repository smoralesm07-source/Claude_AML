#!/usr/bin/env python3
"""Empaqueta la app en un único HTML autocontenido.

La app normal consume el contrato por `fetch`, de modo que abrirla con `file://`
no funciona: el navegador bloquea la petición. Esta versión incrusta CSS, JS y
contrato en un solo archivo que se abre con doble clic, sin servidor.

Es un artefacto derivado: la fuente sigue siendo `app/`. Regenerar con

    python3 tools/build_standalone.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"
OUT = APP / "standalone.html"


def strip_module_syntax(source: str) -> str:
    """Quita import/export para poder concatenar los módulos en un solo script."""
    source = re.sub(r"^import\s+\{[^}]*\}\s+from\s+'[^']*';\s*$", "", source, flags=re.M | re.S)
    source = re.sub(r"^import\s+\{[\s\S]*?\}\s+from\s+'[^']*';\s*$", "", source, flags=re.M)
    return re.sub(r"^export\s+", "", source, flags=re.M)


def main() -> int:
    css = (APP / "assets" / "cockpit.css").read_text(encoding="utf-8")
    charts = strip_module_syntax((APP / "assets" / "charts.js").read_text(encoding="utf-8"))
    cockpit = strip_module_syntax((APP / "assets" / "cockpit.js").read_text(encoding="utf-8"))
    contract = json.loads((APP / "data" / "cockpit_contract_v1.json").read_text(encoding="utf-8"))

    # El contrato deja de pedirse por red y pasa a viajar dentro del archivo.
    cockpit = cockpit.replace(
        "const CONTRACT_URL = new URL('../data/cockpit_contract_v1.json', import.meta.url);",
        "/* El contrato viaja incrustado en esta build autocontenida. */")
    before = cockpit
    cockpit = re.sub(
        r"    const res = await fetch\(CONTRACT_URL\);\n"
        r"    if \(!res\.ok\) throw new Error\(`HTTP \$\{res\.status\}`\);\n"
        r"    app\.data = await res\.json\(\);",
        "    app.data = CONTRACT_DATA;", cockpit)
    if cockpit == before:
        raise SystemExit("No se pudo sustituir el fetch del contrato; revisar app/assets/cockpit.js")

    # El marcado se toma de index.html para no mantener dos copias del cuerpo.
    index = (APP / "index.html").read_text(encoding="utf-8")
    body = index.split("<body>", 1)[1].split("</body>", 1)[0]
    body = re.sub(r'\s*<script type="module"[^>]*></script>', "", body).strip()

    period = contract.get("period_id", "")
    html = f"""<title>IFL Cockpit</title>
<meta name="description" content="Cockpit analítico del ecosistema de radares OSINT con enfoque AML/LA-FT · corte {period}.">
<style>
{css}
</style>

{body}

<script type="module">
const CONTRACT_DATA = {json.dumps(contract, ensure_ascii=False)};

{charts}

{cockpit}
</script>
"""
    OUT.write_text(html, encoding="utf-8")
    size = OUT.stat().st_size
    print(f"Escrito {OUT.relative_to(ROOT)} ({size / 1024:.0f} KB)")
    print(f"  {len(contract['sources'])} fuentes · {len(contract['cases'])} casos · "
          f"{len(contract['sectors'])} actividades UAF")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
