"""Phase 8 EPUB exporter tests that retain artifacts for manual inspection."""

import os
import unittest
import zipfile
from xml.etree import ElementTree as ET

from src.epub_exporter import (
    build_epub,
    get_epub_preview,
    get_epub_status,
    prepare_epub_preview,
    validate_epub_bytes,
)
from src.file_utils import atomic_write_text


ARTIFACT_ROOT = os.path.abspath("tests/artifacts/phase8_test_runtime")


SAMPLE_HTML = """<!doctype html>
<html lang="th"><head><meta charset="utf-8"><title>ต้นฉบับ</title></head>
<body><main>
<section data-page="1"><h1>บทที่ 1 เริ่มต้น</h1><p>ข้อความภาษาไทย &amp; English</p></section>
<section data-page="2"><h2>หัวข้อย่อย</h2><p class="pre-wrap">บรรทัดแรก\nบรรทัดที่สอง</p></section>
<script>alert('must not survive')</script>
</main></body></html>"""


class TestPhase8EpubExporter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.makedirs(ARTIFACT_ROOT, exist_ok=True)

    def make_job(self, name: str, html_content: str = SAMPLE_HTML) -> str:
        export_dir = os.path.join(ARTIFACT_ROOT, name, "export")
        os.makedirs(export_dir, exist_ok=True)
        atomic_write_text(os.path.join(export_dir, "basic.html"), html_content)
        return name

    def test_preview_uses_safe_xhtml_and_same_payload_as_package(self):
        job_id = self.make_job("preview_and_package")
        preview = prepare_epub_preview(
            job_id,
            source_variant="basic",
            metadata={"title": "หนังสือ <ทดสอบ>", "creator": "ผู้เขียน", "language": "th"},
            chapter_split="page",
            files_dir=ARTIFACT_ROOT,
        )
        self.assertEqual(preview["status"], "preview_ready")
        self.assertEqual(preview["chapters_count"], 2)

        preview_xhtml = get_epub_preview(job_id, files_dir=ARTIFACT_ROOT)
        ET.fromstring(preview_xhtml)
        self.assertIn("ข้อความภาษาไทย", preview_xhtml)
        self.assertNotIn("<script", preview_xhtml.lower())

        package = build_epub(job_id, preview["preview_revision"], files_dir=ARTIFACT_ROOT)
        self.assertEqual(package["status"], "ready")
        self.assertTrue(package["validation"]["valid"])

        epub_path = os.path.join(ARTIFACT_ROOT, job_id, "export", "epub", "book.epub")
        with open(epub_path, "rb") as stream:
            package_bytes = stream.read()
        self.assertTrue(validate_epub_bytes(package_bytes)["valid"])
        with zipfile.ZipFile(epub_path, "r") as archive:
            first = archive.infolist()[0]
            self.assertEqual(first.filename, "mimetype")
            self.assertEqual(first.compress_type, zipfile.ZIP_STORED)
            self.assertEqual(archive.read("mimetype"), b"application/epub+zip")
            chapter = archive.read("EPUB/text/chapter-001.xhtml").decode("utf-8")
            self.assertIn("ข้อความภาษาไทย", chapter)
            self.assertNotIn("<script", chapter.lower())

    def test_changed_source_rejects_old_preview_revision(self):
        job_id = self.make_job("revision_conflict")
        preview = prepare_epub_preview(job_id, source_variant="basic", files_dir=ARTIFACT_ROOT)
        source_path = os.path.join(ARTIFACT_ROOT, job_id, "export", "basic.html")
        atomic_write_text(source_path, SAMPLE_HTML.replace("เริ่มต้น", "แก้ไขแล้ว"))

        with self.assertRaisesRegex(ValueError, "Conflict: source HTML changed"):
            build_epub(job_id, preview["preview_revision"], files_dir=ARTIFACT_ROOT)
        self.assertTrue(get_epub_status(job_id, files_dir=ARTIFACT_ROOT)["is_stale"])

    def test_wrong_preview_revision_is_rejected(self):
        job_id = self.make_job("wrong_preview_revision")
        prepare_epub_preview(job_id, source_variant="basic", files_dir=ARTIFACT_ROOT)
        with self.assertRaisesRegex(ValueError, "Conflict: preview revision"):
            build_epub(job_id, "wrong-revision", files_dir=ARTIFACT_ROOT)

    def test_new_preview_marks_previous_package_stale(self):
        job_id = self.make_job("package_stale_after_preview")
        first = prepare_epub_preview(
            job_id,
            source_variant="basic",
            metadata={"title": "ฉบับแรก"},
            files_dir=ARTIFACT_ROOT,
        )
        build_epub(job_id, first["preview_revision"], files_dir=ARTIFACT_ROOT)
        self.assertTrue(get_epub_status(job_id, files_dir=ARTIFACT_ROOT)["epub_ready"])

        second = prepare_epub_preview(
            job_id,
            source_variant="basic",
            metadata={"title": "ฉบับแก้ไข"},
            files_dir=ARTIFACT_ROOT,
        )
        self.assertNotEqual(first["preview_revision"], second["preview_revision"])
        status = get_epub_status(job_id, files_dir=ARTIFACT_ROOT)
        self.assertFalse(status["epub_ready"])
        self.assertTrue(status["package_is_stale"])
        self.assertEqual(status["status"], "preview_ready")

    def test_document_without_exportable_content_is_rejected(self):
        job_id = self.make_job("empty_document", "<html><body><script>bad()</script></body></html>")
        with self.assertRaisesRegex(ValueError, "no exportable"):
            prepare_epub_preview(job_id, source_variant="basic", files_dir=ARTIFACT_ROOT)


if __name__ == "__main__":
    unittest.main()
