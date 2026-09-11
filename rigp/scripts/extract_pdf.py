from __future__ import annotations

import json
import sys
from pathlib import Path

from pypdf import PdfReader, __version__ as pypdf_version


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit("usage: extract_pdf.py <artifact_key> <pdf_path> <output_json>")

    key, pdf_path, out_path = sys.argv[1:4]
    try:
        reader = PdfReader(pdf_path, strict=False)
        pages: list[dict[str, object]] = []
        parts: list[str] = []
        warnings: list[dict[str, object]] = []

        for i, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception as exc:  # extraction failure should not kill the document
                text = ""
                warnings.append({"page": i, "error": str(exc)[:300]})

            text = text.replace("\x00", "").strip()
            pages.append({"page": i, "text": text})
            if text:
                parts.append(f"--- PAGE {i} ---\n{text}")

        full = "\n\n".join(parts)
        if len(full) > 3_900_000:
            full = full[:3_900_000]
            warnings.append({"warning": "TEXT_TRUNCATED_AT_3_9M_CHARS"})

        status = "EXTRACTED" if full.strip() else "EMPTY"
        payload = {
            "artifact_key": key,
            "extractor": "pypdf",
            "extractor_version": pypdf_version,
            "extraction_status": status,
            "page_count": len(reader.pages),
            "extracted_text": full,
            "page_text": pages,
            "metadata": {
                "workflow": "rigp-document-extract",
                "warnings": warnings,
                "source_size_bytes": Path(pdf_path).stat().st_size,
            },
        }
    except Exception as exc:
        payload = {
            "artifact_key": key,
            "extractor": "pypdf",
            "extractor_version": pypdf_version,
            "extraction_status": "FAILED",
            "page_count": 0,
            "extracted_text": "",
            "page_text": [],
            "metadata": {
                "workflow": "rigp-document-extract",
                "error": str(exc)[:500],
            },
        }

    Path(out_path).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(
        json.dumps(
            {
                "artifact_key": key,
                "status": payload["extraction_status"],
                "pages": payload["page_count"],
                "chars": len(payload["extracted_text"]),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
