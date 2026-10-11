import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from src.file_utils import atomic_write_json
from src.translation_core import save_glossary, translation_dir
from src.translation_providers import TranslationError, TranslationProvider
from src.translation_tasks import TranslationTasks, _target_language_mismatch

ROOT=Path(__file__).resolve().parents[2]
FILES=ROOT/"tests"/"artifacts"
JOB="phase10_core_job"


class FakeDB:
    def get_job_status(self,job_id): return object() if job_id==JOB else None


class FakeManager:
    def __init__(self): self.ai_lock=threading.Lock()


class SafeProvider(TranslationProvider):
    name="local"
    def capability(self): return {"provider":"local","available":True,"cloud":False,"model":"fake-safe","languages":[{"code":"en","name":"English"},{"code":"th","name":"ไทย"}]}
    def translate(self,segments,config,glossary): return [{"id":s["id"],"text":"แปล "+s["source_text"]} for s in segments]


class SlowProvider(SafeProvider):
    def translate(self,segments,config,glossary): time.sleep(.1); return super().translate(segments,config,glossary)


class FlakyProvider(SafeProvider):
    def __init__(self): self.calls=0
    def translate(self,segments,config,glossary):
        self.calls+=1
        if self.calls==1: raise TranslationError("temporary","transient",True)
        return super().translate(segments,config,glossary)


class TimeoutProvider(SafeProvider):
    def __init__(self):self.calls=0
    def translate(self,segments,config,glossary):self.calls+=1;raise TranslationError("timeout","timeout",True)


class ControlledProvider(SafeProvider):
    def __init__(self):self.started=threading.Event();self.release=threading.Event()
    def translate(self,segments,config,glossary):self.started.set();self.release.wait(2);return super().translate(segments,config,glossary)


class UnavailableProvider(SafeProvider):
    def capability(self): return {"provider":"local","available":False,"error":"AGY CLI is not authenticated"}


CONFIG={"source_variant":"final","source_language":"auto","target_language":"th","style":"academic","provider":"local","preserve_manual_final":True}


class TranslationTaskTests(unittest.TestCase):
    def test_01_background_completion_exports_and_revision_conflict(self):
        tasks=TranslationTasks(FakeDB(),FakeManager(),str(FILES))
        with patch("src.translation_tasks.get_provider",return_value=SafeProvider()):
            started=tasks.start(JOB,CONFIG)
            self.assertIn(started["status"],{"queued","running"})
            for _ in range(100):
                status=tasks.status(JOB)
                if status["status"] not in {"queued","running","cancelling"}: break
                time.sleep(.01)
        self.assertEqual(status["status"],"completed",status)
        model=tasks.result(JOB)
        self.assertEqual(model["schema_version"],"10.0")
        self.assertEqual(model["detected_language"],"en")
        self.assertTrue((FILES/JOB/"export"/"translation"/"translated.html").is_file())
        first=model["segments"][0]
        saved=tasks.save_final(JOB,[{"id":first["id"],"text":first["final_text"]+" แก้มือ"}],model["translation_revision"])
        self.assertTrue(next(s for s in saved["segments"] if s["id"]==first["id"])["manual_edited"])
        with self.assertRaisesRegex(ValueError,"Conflict"):
            tasks.save_final(JOB,[],model["translation_revision"])
        save_glossary(str(FILES),JOB,[{"source":f"term-{time.time_ns()}","target":"","do_not_translate":True}])
        stale=tasks.result(JOB)
        self.assertTrue(stale["stale"]);self.assertIn("glossary_revision_changed",stale["stale_reasons"])

    def test_02_cancel_is_cooperative(self):
        tasks=TranslationTasks(FakeDB(),FakeManager(),str(FILES))
        with patch("src.translation_tasks.get_provider",return_value=SlowProvider()):
            tasks.start(JOB,CONFIG); tasks.cancel(JOB)
            for _ in range(300):
                status=tasks.status(JOB)
                if status["status"] not in {"queued","running","cancelling"}: break
                time.sleep(.01)
        self.assertEqual(status["status"],"cancelled")

    def test_03_transient_retry_and_restart_state(self):
        tasks=TranslationTasks(FakeDB(),FakeManager(),str(FILES));provider=FlakyProvider()
        with patch("src.translation_tasks.get_provider",return_value=provider):
            tasks.start(JOB,CONFIG)
            for _ in range(100):
                status=tasks.status(JOB)
                if status["status"] not in {"queued","running","cancelling"}: break
                time.sleep(.01)
        self.assertEqual(status["status"],"completed",status);self.assertGreaterEqual(provider.calls,2)
        calls=provider.calls
        with patch("src.translation_tasks.get_provider",return_value=provider):
            tasks.start(JOB,CONFIG,resume=True)
            for _ in range(100):
                resumed=tasks.status(JOB)
                if resumed["status"] not in {"queued","running","cancelling"}:break
                time.sleep(.01)
        self.assertEqual(resumed["status"],"completed");self.assertEqual(provider.calls,calls)
        progress=Path(translation_dir(str(FILES),JOB))/"progress.json"
        atomic_write_json(str(progress),{"job_id":JOB,"status":"running","started_at":time.time(),"updated_at":time.time()})
        restarted=TranslationTasks(FakeDB(),FakeManager(),str(FILES)).status(JOB)
        self.assertEqual(restarted["status"],"failed");self.assertTrue(restarted["retryable"])

    def test_04_target_language_validation(self):
        segments=[{"status":"translated","translated_text":"This response stayed fully in English and is long enough to validate"}]
        self.assertTrue(_target_language_mismatch(segments,"th"))
        segments[0]["translated_text"]="ผลการแปลภาษาไทยที่ยาวพอสำหรับตรวจภาษาปลายทางและมีเนื้อหาครบถ้วน"
        self.assertFalse(_target_language_mismatch(segments,"th"))

    def test_05_timeout_retries_then_fails(self):
        tasks=TranslationTasks(FakeDB(),FakeManager(),str(FILES));provider=TimeoutProvider()
        with patch("src.translation_tasks.get_provider",return_value=provider):
            tasks.start(JOB,CONFIG)
            for _ in range(300):
                status=tasks.status(JOB)
                if status["status"] not in {"queued","running","cancelling"}:break
                time.sleep(.01)
        self.assertEqual(status["status"],"failed");self.assertEqual(status["error_code"],"timeout");self.assertEqual(provider.calls,3)

    def test_06_source_change_during_task_fails_stale(self):
        tasks=TranslationTasks(FakeDB(),FakeManager(),str(FILES));provider=ControlledProvider();source=FILES/JOB/"export"/"final.html";original=source.read_text(encoding="utf-8")
        try:
            with patch("src.translation_tasks.get_provider",return_value=provider):
                tasks.start(JOB,CONFIG);self.assertTrue(provider.started.wait(1));source.write_text(original+"<!-- changed -->",encoding="utf-8");provider.release.set()
                for _ in range(100):
                    status=tasks.status(JOB)
                    if status["status"] not in {"queued","running","cancelling"}:break
                    time.sleep(.01)
            self.assertEqual(status["status"],"failed");self.assertEqual(status["error_code"],"stale")
        finally: source.write_text(original,encoding="utf-8")

    def test_07_start_rejects_unavailable_provider_before_creating_task(self):
        tasks=TranslationTasks(FakeDB(),FakeManager(),str(FILES))
        with patch("src.translation_tasks.get_provider",return_value=UnavailableProvider()):
            with self.assertRaisesRegex(ValueError,"not authenticated"):
                tasks.start(JOB,CONFIG)
        self.assertFalse(tasks.is_active(JOB))


if __name__=="__main__": unittest.main()
