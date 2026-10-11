import json
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from src.epub_exporter import build_epub, prepare_epub_preview
from src.translation_core import create_model, export_results, save_model
from src import server

ROOT=Path(__file__).resolve().parents[2]
FILES=ROOT/"tests"/"artifacts"
JOB="phase10_api_job"


class FakeDB:
    def get_job_status(self,job_id):
        if job_id!=JOB:return None
        return type("Job",(),{"filename":"source.pdf"})()


class FakeTasks:
    def __init__(self): self.cancelled=False
    def start(self,job_id,config,resume=False): return {"job_id":job_id,"status":"queued","resume":resume}
    def status(self,job_id): return {"job_id":job_id,"status":"running","batch_count":2,"completed_batches":1}
    def cancel(self,job_id): self.cancelled=True;return {"job_id":job_id,"status":"cancelling"}
    def result(self,job_id): return {"status":"completed","stale":False,"translation_revision":"r1","segments":[]}
    def save_final(self,job_id,edits,base_revision): return {"status":"completed","translation_revision":"r2","segments":edits}


class Phase10ApiAndEpubTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        export=FILES/JOB/"export";export.mkdir(parents=True,exist_ok=True)
        (export/"final.html").write_text('<html><body><h1 id="chapter">Guide</h1><p data-block-id="p1">Price $20</p></body></html>',encoding="utf-8")
        (FILES/JOB/"final.txt").write_text("Price < $20 & safe",encoding="utf-8")
        translated=FILES/"phase10_epub_job"/"export";translated.mkdir(parents=True,exist_ok=True)
        (translated/"final.html").write_text('<!doctype html><html lang="en"><body><h1 id="chapter">Guide</h1><table><tr><td data-cell-id="c1">Price $20</td></tr></table></body></html>',encoding="utf-8")

    def test_01_api_contract_validation_and_lifecycle(self):
        fake=FakeTasks()
        config={"source_variant":"final","source_language":"en","target_language":"th","style":"academic","provider":"local"}
        route_paths={route.path for route in server.app.routes}
        for path in ("/api/translation/capabilities","/api/jobs/{job_id}/translation/estimate","/api/jobs/{job_id}/translation/start",
                     "/api/jobs/{job_id}/translation/progress","/api/jobs/{job_id}/translation/cancel","/api/jobs/{job_id}/translation/retry",
                     "/api/jobs/{job_id}/translation/result","/api/jobs/{job_id}/translation/final","/api/jobs/{job_id}/translation/export/{format_name}",
                     "/api/jobs/{job_id}/translation/source/preview"):
            self.assertIn(path,route_paths)
        req=server.TranslationStartRequest(**config)
        with patch("src.server.db",FakeDB()),patch("src.server.translation_tasks",fake),patch("src.server.DEFAULT_OUTPUT_DIR",str(FILES)):
            self.assertEqual(server.start_translation_endpoint(JOB,req)["status"],"queued")
            self.assertEqual(server.translation_progress_endpoint(JOB)["status"],"running")
            self.assertEqual(server.cancel_translation_endpoint(JOB)["status"],"cancelling")
            self.assertEqual(server.retry_translation_endpoint(JOB,server.TranslationConfigRequest(**config))["resume"],True)
            self.assertEqual(server.translation_result_endpoint(JOB)["translation_revision"],"r1")
            self.assertEqual(server.save_translation_final_endpoint(JOB,server.TranslationSaveFinalRequest(edits=[],base_revision="r1"))["translation_revision"],"r2")
            estimate=server.estimate_translation_endpoint(JOB,server.TranslationConfigRequest(**config))
            self.assertGreater(estimate["characters"],0)
            glossary=server.save_translation_glossary_endpoint(JOB,server.TranslationGlossaryRequest(entries=[{"source":"API","target":"","do_not_translate":True}]))
            self.assertTrue(glossary["revision"])
            preview=server.preview_translation_source_endpoint(JOB,"final")
            self.assertIn(b"Price $20",preview.body);self.assertEqual(preview.headers["x-translation-source-variant"],"final")
            text_preview=server.preview_translation_source_endpoint(JOB,"text_final")
            self.assertIn(b"Price &lt; $20 &amp; safe",text_preview.body)
        with self.assertRaises(ValidationError): server.TranslationConfigRequest(**{**config,"target_language":""})

    def test_02_translated_epub_uses_existing_quick_preview_guards(self):
        job="phase10_epub_job"
        model=create_model(str(FILES),job,{"source_variant":"final","source_language":"en","target_language":"th","style":"academic","provider":"local"})
        translated={"Guide":"คู่มือ","Price $20":"ราคา $20"}
        for segment in model["segments"]:
            if segment["status"]=="pending": segment.update(translated_text=translated[segment["source_text"]],final_text=translated[segment["source_text"]],status="translated")
        model["status"]="completed";save_model(str(FILES),job,model);export_results(str(FILES),job,model)
        preview=prepare_epub_preview(job,source_variant="translated",chapter_split="heading",files_dir=str(FILES),metadata={"title":"Phase 10","language":"th"})
        result=build_epub(job,preview["preview_revision"],files_dir=str(FILES))
        book=FILES/job/"export"/"epub"/"book.epub"
        self.assertTrue(book.is_file());self.assertEqual(result["validation"]["errors"],[])
        with zipfile.ZipFile(book) as archive:
            content="\n".join(archive.namelist());self.assertIn("nav.xhtml",content)
            text="\n".join(archive.read(name).decode("utf-8") for name in archive.namelist() if name.endswith(".xhtml"))
            self.assertIn("คู่มือ",text);self.assertIn("<table><tr><td>ราคา $20</td></tr></table>",text)
        source=FILES/job/"export"/"final.html";original=source.read_text(encoding="utf-8")
        try:
            source.write_text(original.replace("Guide","Changed Guide"),encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"stale"):
                prepare_epub_preview(job,source_variant="translated",chapter_split="heading",files_dir=str(FILES),metadata={"title":"Phase 10","language":"th"})
        finally: source.write_text(original,encoding="utf-8")

    def test_03_google_config_endpoints_and_page(self):
        from fastapi.testclient import TestClient
        import tempfile
        from src import config

        client = TestClient(server.app)

        # 1. Config HTML page includes Google Cloud Translation section
        page = client.get("/config.html")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Google Cloud Translation", page.text)
        self.assertIn("google-project", page.text)
        self.assertIn("google-location", page.text)
        self.assertIn("google-credentials-path", page.text)
        self.assertIn("google-api-key", page.text)
        self.assertIn("btn-test-google", page.text)
        self.assertIn("btn-save-google", page.text)

        # 2. GET /api/translation/google/config returns non-secret fields
        res = client.get("/api/translation/google/config")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("project", data)
        self.assertIn("location", data)
        self.assertIn("credentials_configured", data)
        self.assertIn("api_key_configured", data)
        self.assertNotIn("api_key", data)

        # 3. PUT /api/translation/google/config saves to .env
        old_env = config.ENV_PATH
        try:
            with tempfile.TemporaryDirectory() as td:
                config.ENV_PATH = Path(td) / ".env"
                save_res = client.put(
                    "/api/translation/google/config",
                    json={
                        "project": "my-test-gcp-project",
                        "location": "global",
                        "credentials_path": "C:\\keys\\fake.json",
                        "api_key": "AIzaSyTest123",
                    }
                )
                self.assertEqual(save_res.status_code, 200)
                saved_data = save_res.json()
                self.assertEqual(saved_data["project"], "my-test-gcp-project")
                self.assertEqual(saved_data["location"], "global")
                self.assertTrue(saved_data["api_key_configured"])
                self.assertNotIn("api_key", saved_data)

                content = config.ENV_PATH.read_text(encoding="utf-8")
                self.assertIn("GOOGLE_CLOUD_PROJECT=my-test-gcp-project", content)
                self.assertIn("GOOGLE_CLOUD_LOCATION=global", content)
                self.assertIn("GOOGLE_TRANSLATION_API_KEY=AIzaSyTest123", content)
        finally:
            config.ENV_PATH = old_env

        # 4. POST /api/translation/google/test returns error if not configured
        with patch.dict("os.environ", {"GOOGLE_APPLICATION_CREDENTIALS": "", "GOOGLE_TRANSLATION_API_KEY": ""}):
            test_res = client.post("/api/translation/google/test", json={})
            self.assertEqual(test_res.status_code, 200)
            self.assertEqual(test_res.json()["status"], "error")


if __name__=="__main__": unittest.main()

