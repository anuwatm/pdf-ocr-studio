import json
import base64
import io
import os
import uuid
import zipfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from src.database import JobDatabase
from src.epub_exporter import (_parse_blocks, build_epub, get_epub_status,
                               prepare_epub_preview, validate_epub_bytes)
from src.server import app
from src.html_exporter import sanitize_final_html
from src.toc_editor import editor_state, save_editor_toc


ROOT = os.path.abspath("tests/artifacts/phase9_runtime")


def make_job(markup=None):
    job_id = "phase9_" + uuid.uuid4().hex[:12]
    export = os.path.join(ROOT, job_id, "export")
    os.makedirs(export, exist_ok=True)
    content = markup or """<!doctype html><html><body><main>
      <h1 id="thai-intro">บทนำ &amp; ภาพรวม</h1><p>ข้อความเดิม</p>
      <h2 id="same-a">ชื่อซ้ำ</h2><p>ก</p><h2 id="same-b">ชื่อซ้ำ</h2><p>ข</p>
      <h1 id="chapter-two">บทที่ ๒</h1><p>เนื้อหาสอง</p>
    </main></body></html>"""
    with open(os.path.join(export, "basic.html"), "w", encoding="utf-8") as stream:
        stream.write(content)
    return job_id


class TestTocModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.makedirs(ROOT, exist_ok=True)

    def test_stable_heading_ids_preserve_html_ids_and_generated_hashes(self):
        sanitized = sanitize_final_html("<h1 id='kept'>A</h1><h2 id='second'>B</h2>")
        self.assertIn('id="kept"', sanitized)
        self.assertIn('id="second"', sanitized)
        blocks = _parse_blocks("<html><body><h1 id='kept'>A</h1><h2>B</h2></body></html>")
        before = {block["visible_text"]: block["id"] for block in blocks if block["tag"].startswith("h")}
        blocks = _parse_blocks("<html><body><h1 id='new'>New</h1><h1 id='kept'>A</h1><h2>B</h2></body></html>")
        after = {block["visible_text"]: block["id"] for block in blocks if block["tag"].startswith("h")}
        self.assertEqual(before["A"], "kept")
        self.assertEqual(before["A"], after["A"])
        self.assertEqual(before["B"], after["B"])
        duplicate = _parse_blocks("<html><body><h1 id='dup'>A</h1><h1 id='dup'>B</h1></body></html>")
        self.assertEqual(len({block["id"] for block in duplicate}), 2)
        self.assertEqual(duplicate[1]["id_source"], "duplicate-remapped")

    def test_edit_save_reload_preview_package_and_chapter_split(self):
        job = make_job()
        state = editor_state(job, ROOT)
        entries = state["entries"]
        entries[0]["label"] = "สารบัญไทย <ปลอดภัย>"
        entries[1], entries[2] = entries[2], entries[1]
        for index, entry in enumerate(entries):
            entry["order"] = index
            entry["status"] = "user-edited"
        entries[1]["parent_id"] = entries[0]["entry_id"]
        entries[1]["level"] = 2
        saved = save_editor_toc(job, entries, state["source_revision"], state["toc_revision"],
                                state["base_preview_revision"], ROOT)
        reloaded = editor_state(job, ROOT)
        self.assertEqual(reloaded["entries"][0]["label"], "สารบัญไทย <ปลอดภัย>")
        self.assertEqual(saved["toc_revision"], reloaded["toc_revision"])

        preview = prepare_epub_preview(job, files_dir=ROOT, chapter_split="heading",
                                       toc_revision=saved["toc_revision"])
        self.assertEqual(preview["toc_mode"], "edited")
        payload_path = os.path.join(ROOT, job, "export", "epub", "preview_payload.json")
        with open(payload_path, encoding="utf-8") as stream:
            payload = json.load(stream)
        self.assertIn("สารบัญไทย &lt;ปลอดภัย&gt;", payload["nav_xhtml"])
        self.assertEqual(len(payload["chapters"]), 2)
        content_before = "".join(chapter["xhtml"] for chapter in payload["chapters"])

        page_preview = prepare_epub_preview(job, files_dir=ROOT, chapter_split="page",
                                            toc_revision=saved["toc_revision"])
        with open(payload_path, encoding="utf-8") as stream:
            page_payload = json.load(stream)
        content_after = "".join(chapter["xhtml"] for chapter in page_payload["chapters"])
        self.assertIn("ข้อความเดิม", content_before)
        self.assertIn("ข้อความเดิม", content_after)
        result = build_epub(job, page_preview["preview_revision"], files_dir=ROOT)
        self.assertTrue(result["validation"]["valid"])
        package_path = os.path.join(ROOT, job, "export", "epub", "book.epub")
        with open(package_path, "rb") as stream:
            self.assertTrue(validate_epub_bytes(stream.read())["valid"])
        with zipfile.ZipFile(package_path) as package:
            nav = package.read("EPUB/nav.xhtml").decode("utf-8")
            self.assertIn("สารบัญไทย &lt;ปลอดภัย&gt;", nav)
            self.assertIn("#same-b", nav)
        with open(package_path, "rb") as stream:
            first_bytes = stream.read()
        build_epub(job, page_preview["preview_revision"], files_dir=ROOT)
        with open(package_path, "rb") as stream:
            self.assertEqual(first_bytes, stream.read())

    def test_source_change_rematch_missing_and_stale_package(self):
        job = make_job()
        state = editor_state(job, ROOT)
        saved = save_editor_toc(job, state["entries"], state["source_revision"], state["toc_revision"],
                                state["base_preview_revision"], ROOT)
        preview = prepare_epub_preview(job, files_dir=ROOT, toc_revision=saved["toc_revision"])
        build_epub(job, preview["preview_revision"], files_dir=ROOT)
        path = os.path.join(ROOT, job, "export", "basic.html")
        with open(path, encoding="utf-8") as stream:
            changed = stream.read().replace('<h2 id="same-a">ชื่อซ้ำ</h2>', "")
        with open(path, "w", encoding="utf-8") as stream:
            stream.write(changed)
        rematched = editor_state(job, ROOT)
        self.assertTrue(rematched["source_changed"])
        self.assertEqual(len(rematched["unresolved"]), 1)
        self.assertEqual(get_epub_status(job, ROOT)["status"], "stale")
        with self.assertRaisesRegex(ValueError, "edited TOC is stale"):
            prepare_epub_preview(job, files_dir=ROOT)

    def test_unique_rematch_and_ambiguous_heading_are_explicit(self):
        job = make_job("<html><body><h1 id='old'>หัวข้อเฉพาะ</h1><h2 id='dup-a'>ซ้ำ</h2><h2 id='dup-b'>ซ้ำ</h2></body></html>")
        state = editor_state(job, ROOT)
        save_editor_toc(job, state["entries"], state["source_revision"], state["toc_revision"],
                        state["base_preview_revision"], ROOT)
        path = os.path.join(ROOT, job, "export", "basic.html")
        with open(path, "w", encoding="utf-8") as stream:
            stream.write("<html><body><h1 id='new'>หัวข้อเฉพาะ</h1><h2 id='dup-c'>ซ้ำ</h2><h2 id='dup-d'>ซ้ำ</h2></body></html>")
        rematched = editor_state(job, ROOT)
        unique = next(entry for entry in rematched["entries"] if entry["label"] == "หัวข้อเฉพาะ")
        duplicate = [entry for entry in rematched["entries"] if entry["label"] == "ซ้ำ"]
        self.assertEqual(unique["resolution"], "unique-rematch")
        self.assertTrue(all(entry["status"] == "unresolved" for entry in duplicate))
        self.assertTrue(all(entry["resolution"] == "ambiguous" for entry in duplicate))

    def test_validation_and_conflicts(self):
        job = make_job()
        state = editor_state(job, ROOT)
        cases = []
        empty = []
        cases.append(empty)
        blank = [dict(state["entries"][0], label=" ")]
        cases.append(blank)
        orphan = [dict(state["entries"][0], level=2, parent_id="missing")]
        cases.append(orphan)
        no_target = [dict(state["entries"][0], target_id="missing")]
        cases.append(no_target)
        too_deep = [dict(state["entries"][0], level=4)]
        cases.append(too_deep)
        for entries in cases:
            with self.assertRaises(ValueError):
                save_editor_toc(job, entries, state["source_revision"], state["toc_revision"],
                                state["base_preview_revision"], ROOT)
        changed_entries = [dict(entry) for entry in state["entries"]]
        changed_entries[0]["label"] += " changed"
        save_editor_toc(job, changed_entries, state["source_revision"], state["toc_revision"],
                        state["base_preview_revision"], ROOT)
        with self.assertRaisesRegex(ValueError, "TOC revision changed"):
            save_editor_toc(job, state["entries"], state["source_revision"], state["toc_revision"],
                            state["base_preview_revision"], ROOT)

    def test_toc_save_preserves_cover_metadata_and_preview_config(self):
        job = make_job()
        image = io.BytesIO(); Image.new("RGB", (32, 48), "blue").save(image, "PNG")
        first = prepare_epub_preview(job, files_dir=ROOT, metadata={"title":"เดิม","creator":"ผู้เขียน"},
                                     cover={"data_base64":base64.b64encode(image.getvalue()).decode(),"alt":"ปกเดิม"})
        payload_path = os.path.join(ROOT, job, "export", "epub", "preview_payload.json")
        with open(payload_path, encoding="utf-8") as stream: before = json.load(stream)
        state = editor_state(job, ROOT)
        entries = [dict(entry) for entry in state["entries"]]; entries[0]["label"] = "แก้เฉพาะสารบัญ"
        saved = save_editor_toc(job, entries, state["source_revision"], state["toc_revision"],
                                first["preview_revision"], ROOT)
        with open(payload_path, encoding="utf-8") as stream: unchanged = json.load(stream)
        self.assertEqual(before["cover"]["sha256"], unchanged["cover"]["sha256"])
        self.assertEqual(before["metadata"], unchanged["metadata"])
        second = prepare_epub_preview(job, files_dir=ROOT, metadata=before["metadata"], cover={"reuse":True},
                                      toc_revision=saved["toc_revision"])
        self.assertEqual(second["cover"]["sha256"], before["cover"]["sha256"])
        self.assertNotEqual(second["preview_revision"], first["preview_revision"])


class TestTocEndpoints(unittest.TestCase):
    def test_get_save_regenerate_and_409(self):
        job = make_job()
        database = JobDatabase(os.path.join(ROOT, "jobs.db"))
        database.create_job(job, "phase9.pdf", os.path.join(ROOT, "phase9.pdf"), 1, 1, False)
        with patch("src.server.DEFAULT_OUTPUT_DIR", ROOT), patch("src.server.db", database):
            client = TestClient(app)
            state = client.get(f"/api/jobs/{job}/export/epub/toc").json()
            payload = {
                "entries": state["entries"], "base_source_revision": state["source_revision"],
                "base_toc_revision": state["toc_revision"],
                "base_preview_revision": state["base_preview_revision"],
            }
            payload["entries"][0]["label"] += " changed"
            response = client.put(f"/api/jobs/{job}/export/epub/toc", json=payload)
            self.assertEqual(response.status_code, 200, response.text)
            stale = client.put(f"/api/jobs/{job}/export/epub/toc", json=payload)
            self.assertEqual(stale.status_code, 409)
            latest = client.get(f"/api/jobs/{job}/export/epub/toc").json()
            regenerate = client.post(f"/api/jobs/{job}/export/epub/toc/regenerate", json={
                "confirm": True, "base_source_revision": latest["source_revision"],
                "base_toc_revision": latest["toc_revision"],
                "base_preview_revision": latest["base_preview_revision"],
            })
            self.assertEqual(regenerate.status_code, 200, regenerate.text)


if __name__ == "__main__":
    unittest.main()
