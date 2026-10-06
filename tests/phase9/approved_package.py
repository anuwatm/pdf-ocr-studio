import base64
import hashlib
import json
from pathlib import Path

from src.epub_exporter import build_epub, prepare_epub_preview
from src.toc_editor import editor_state, save_editor_toc


ROOT = Path(__file__).resolve().parents[2]
FILES = ROOT / "tests/artifacts"
JOB = "approved_44pages_job"


def main():
    source = FILES / JOB / "export/basic.html"
    if not source.is_file():
        raise RuntimeError("Approved 44-page Phase 7 HTML artifact is required")
    state = editor_state(JOB, str(FILES), "basic", "page")
    entries = [dict(entry) for entry in state["entries"]]
    entries[0]["label"] = "สารบัญ Phase 9 — ฉบับตรวจรับ"
    entries[0]["status"] = "user-edited"
    saved = save_editor_toc(JOB, entries, state["source_revision"], state["toc_revision"],
                            state["base_preview_revision"], str(FILES), "basic", "page")
    cover_bytes = (ROOT / "demo/01.png").read_bytes()
    preview = prepare_epub_preview(
        JOB, source_variant="basic", chapter_split="page", files_dir=str(FILES),
        metadata={"title":"เอกสาร OCR 44 หน้า — Phase 9", "language":"th"},
        cover={"data_base64":base64.b64encode(cover_bytes).decode(), "alt":"ปกจาก demo/01.png"},
        toc_revision=saved["toc_revision"],
    )
    result = build_epub(JOB, preview["preview_revision"], files_dir=str(FILES))
    source_book = FILES / JOB / "export/epub/book.epub"
    target = ROOT / "phase9/approved_phase9.epub"
    target.parent.mkdir(exist_ok=True)
    target.write_bytes(source_book.read_bytes())
    report = {
        "scope":"Approved 44-page OCR HTML from Phase 7/8; editable TOC and PNG cover",
        "source_sha256":hashlib.sha256(source.read_bytes()).hexdigest(),
        "toc_revision":saved["toc_revision"], "preview_revision":preview["preview_revision"],
        "toc_entries":preview["toc_entries_count"], "chapters":preview["chapters_count"],
        "epub_sha256":result["sha256"], "bytes":result["file_size"], "validation":result["validation"],
    }
    (ROOT / "phase9/package_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__": main()
