import json
import os
from pathlib import Path

import pdfplumber


DOWNLOADS = Path.home() / "Downloads"
OUTPUT = Path(__file__).parent / "output"


FIELD_TYPE_MAP = {
    "/Btn": "checkbox",  # could also be radio; refined below
    "/Tx": "text",
    "/Ch": "choice",
    "/Sig": "signature",
}

RADIO_FLAG = 1 << 16  # bit 16 in /Ff marks a radio button


def _parse_form_fields(pdf) -> dict[str, dict]:
    """Walk the AcroForm field tree and return {fully_qualified_name: field_meta}."""
    fields: dict[str, dict] = {}

    def walk(node, prefix: str = ""):
        kids = node.get("/Kids")
        t = node.get("/T")
        name = f"{prefix}.{t}" if prefix else (t or "")

        if kids and isinstance(kids, list):
            first = kids[0]
            if isinstance(first, dict) and first.get("/FT"):
                # terminal widget with merged parent data
                walk(first, prefix)
            else:
                for kid in kids:
                    # merge parent attributes into kid
                    merged = dict(node)
                    merged.update(kid)
                    walk(merged, prefix if t is None else name)
        elif node.get("/FT"):
            ff = node.get("/Ff", 0)
            ft_raw = node.get("/FT", "")
            ftype = FIELD_TYPE_MAP.get(ft_raw, ft_raw)
            if ft_raw == "/Btn" and (ff & RADIO_FLAG):
                ftype = "radio"

            meta = {
                "type": ftype,
                "value": _norm_val(node.get("/V")),
                "flags": ff,
                "rect": node.get("/Rect"),
            }
            # For radio / checkbox, also record default / appearance state
            if ftype in ("checkbox", "radio"):
                meta["appearance"] = _norm_val(node.get("/AS"))

            fields[name or "<unnamed>"] = meta

    acro = pdf.doc.catalog.get("/AcroForm")
    if acro is None:
        return fields
    for field in (acro.get("/Fields") or acro.get("/fields") or []):
        walk(field)
    return fields


def _norm_val(v):
    if isinstance(v, bytes):
        try:
            return v.decode("utf-8")
        except UnicodeDecodeError:
            return v.decode("latin-1", errors="replace")
    return v


def _parse_annot_form_fields(page) -> list[dict]:
    """Extract widget annotations that are *not* part of the global AcroForm tree."""
    fields = []
    for a in (page.annots or []):
        d = a.get("data", {})
        if d.get("/Subtype") != "/Widget":
            continue
        ft_raw = d.get("/FT", "")
        ftype = FIELD_TYPE_MAP.get(ft_raw, ft_raw)
        ff = d.get("/Ff", 0)
        if ft_raw == "/Btn" and (ff & RADIO_FLAG):
            ftype = "radio"
        fields.append(
            {
                "type": ftype,
                "name": _norm_val(d.get("/T")),
                "value": _norm_val(d.get("/V")),
                "appearance": _norm_val(d.get("/AS")),
                "rect": d.get("/Rect"),
            }
        )
    return fields


def extract_pdf(pdf_path: Path) -> dict:
    result = {"file": pdf_path.name, "pages": []}
    with pdfplumber.open(pdf_path) as pdf:
        global_fields = _parse_form_fields(pdf)
        if global_fields:
            result["form_fields"] = global_fields

        for i, page in enumerate(pdf.pages, 1):
            text = page.extract_text()
            tables = page.extract_tables()
            page_data: dict = {"page_number": i, "text": text.strip() if text else ""}
            if tables:
                page_data["tables"] = [[str(c) if c else "" for c in row] for row in tables]

            annot_fields = _parse_annot_form_fields(page)
            if annot_fields:
                page_data["form_fields"] = annot_fields

            result["pages"].append(page_data)
    return result


def main():
    OUTPUT.mkdir(exist_ok=True)
    pdf_files = sorted(DOWNLOADS.glob("*.pdf"))
    if not pdf_files:
        print(f"No PDF files found in {DOWNLOADS}")
        return

    for pdf_path in pdf_files:
        print(f"Processing: {pdf_path.name}")
        try:
            data = extract_pdf(pdf_path)
            out_path = OUTPUT / f"{pdf_path.stem}.json"
            with open(out_path, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"  -> Saved to {out_path}")
        except Exception as e:
            print(f"  -> ERROR: {e}")


if __name__ == "__main__":
    main()
