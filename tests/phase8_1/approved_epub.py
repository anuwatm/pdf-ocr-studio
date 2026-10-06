import json
import os
from pathlib import Path

import fitz

from src.epub_exporter import build_epub, prepare_epub_preview
from src.file_utils import atomic_write_json, atomic_write_text
from src.pipeline import ProcessingPipeline
from src.structured_layout import apply_ocr_to_tables, build_page_layout, extract_pdf_vector_tables, generate_structured_exports


ROOT = Path(__file__).resolve().parents[2]
if not (ROOT / "demo" / "04.pdf").is_file():
    ROOT = ROOT.parent
ARTIFACTS = Path.cwd() / "tests" / "artifacts" / "phase8_1_approved_epub"
JOB = "approved_demo04_structured"


def main():
    job_dir = ARTIFACTS / JOB
    job_dir.mkdir(parents=True, exist_ok=True)
    result = ProcessingPipeline(ocr_engine=object()).process_file(
        str(ROOT / "demo" / "04.pdf"), job_id=JOB, output_dir=str(job_dir), page_range=[1]
    )
    fixture = ROOT / "tests" / "artifacts" / "table04_20261005" / "oneocr.json"
    with fixture.open(encoding="utf-8") as stream:
        lines = json.load(stream)["lines"]
    with fitz.open(ROOT / "demo" / "04.pdf") as document:
        tables = apply_ocr_to_tables(extract_pdf_vector_tables(document[0], dpi=300), lines)
    result["pages"][0]["layout"] = build_page_layout(result["pages"][0], tables)
    atomic_write_json(str(job_dir / "ocr.json"), result)
    page_dir = job_dir / "page_01"
    page_dir.mkdir(exist_ok=True)
    for name in ("raw.txt", "corrected.txt", "final.txt"):
        atomic_write_text(str(page_dir / name), result["pages"][0]["raw_text"])
    generate_structured_exports(JOB, files_dir=str(ARTIFACTS))
    preview = prepare_epub_preview(JOB, source_variant="structured", chapter_split="page",
                                   metadata={"title": "ตาราง 04", "language": "th"},
                                   files_dir=str(ARTIFACTS))
    meta = build_epub(JOB, preview["preview_revision"], files_dir=str(ARTIFACTS))
    package = job_dir / "export" / "epub" / "book.epub"
    target = Path.cwd() / "phase8_1" / "approved_structured.epub"
    target.write_bytes(package.read_bytes())
    print(json.dumps({"epub": str(target), "bytes": target.stat().st_size,
                      "validation": meta["validation"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
