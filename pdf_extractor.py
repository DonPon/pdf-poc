import json
import os
from pathlib import Path

import pdfplumber


DOWNLOADS = Path.home() / "Downloads"
OUTPUT = Path(__file__).parent / "output"


def extract_pdf(pdf_path: Path) -> dict:
    result = {"file": pdf_path.name, "pages": []}
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            text = page.extract_text()
            tables = page.extract_tables()
            page_data = {"page_number": i, "text": text.strip() if text else ""}
            if tables:
                page_data["tables"] = [[str(c) if c else "" for c in row] for row in tables]
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
