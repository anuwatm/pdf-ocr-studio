"""Background lifecycle tests. No live LLM requests or file deletion."""
import copy
import json
import threading
import unittest
from contextlib import ExitStack
from unittest.mock import Mock, mock_open, patch

from src.html_ai_tasks import HtmlAiTasks


class HtmlAiTasksTests(unittest.TestCase):
    def setUp(self):
        self.db = Mock()
        self.db.get_job_status.return_value = object()
        self.manager = Mock()
        self.manager.is_ai_in_use.return_value = False
        self.manager.ai_lock = threading.Lock()
        self.tasks = HtmlAiTasks(self.db, self.manager, "files")
        self.writes = []
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch("src.html_ai_tasks.atomic_write_json",
                                      side_effect=lambda path, data: self.writes.append(copy.deepcopy(data))))
        self.client = Mock()
        self.client.timeout = 90
        self.client.check_health.return_value = {"status": "connected"}
        self.stack.enter_context(patch("src.html_ai_tasks.LocalLLMClient", return_value=self.client))

    def join(self, job_id):
        self.tasks._tasks[job_id]["thread"].join(timeout=2)
        self.assertFalse(self.tasks._tasks[job_id]["thread"].is_alive())

    def test_returns_promptly_progress_deduplicates_and_cancels(self):
        entered = threading.Event()
        release = threading.Event()
        self.addCleanup(release.set)
        def generate(*args, **kw):
            kw["progress_callback"](stage="waiting_ai", chunk_count=5,
                                    current_chunk=2, completed_chunks=1)
            entered.set()
            release.wait(timeout=2)
            return "basic", {"validator_status": "cancelled" if kw["cancel_requested"]() else "passed"}
        self.stack.enter_context(patch("src.html_ai_tasks.generate_ai_html", side_effect=generate))
        first = self.tasks.start("job_progress")
        self.assertEqual(first["status"], "running")
        self.assertTrue(entered.wait(timeout=1))
        state = self.tasks.status("job_progress")
        self.assertEqual(state["completed_chunks"], 1)
        self.assertEqual(state["current_chunk"], 2)
        self.assertEqual(state["chunk_count"], 5)
        self.assertEqual(state["timeout_seconds"], 90)
        self.assertEqual(first["task_id"], self.tasks.start("job_progress")["task_id"])
        self.assertEqual(self.tasks.cancel("job_progress")["status"], "cancelling")
        release.set()
        self.join("job_progress")
        self.assertEqual(self.tasks.status("job_progress")["status"], "cancelled")
        self.assertFalse(self.manager.ai_lock.locked())

    def test_success_and_precise_failure(self):
        with patch("src.html_ai_tasks.generate_ai_html", return_value=("html", {"validator_status": "passed"})):
            self.tasks.start("job_success")
            self.join("job_success")
        self.assertEqual(self.tasks.status("job_success")["status"], "completed")
        self.assertTrue(self.tasks.status("job_success")["ai_applied"])
        with patch("src.html_ai_tasks.generate_ai_html", return_value=("basic", {
                "validator_status": "error", "error": "Timeout after 90s", "failed_chunk": 3})):
            self.tasks.start("job_failure")
            self.join("job_failure")
        state = self.tasks.status("job_failure")
        self.assertEqual(state["status"], "failed")
        self.assertEqual(state["error"], "Timeout after 90s")
        self.assertEqual(state["meta"]["failed_chunk"], 3)

    def test_other_ai_task_blocks_dispatch(self):
        self.manager.ai_lock.acquire()
        with self.assertRaises(ValueError):
            self.tasks.start("job_busy")
        self.manager.ai_lock.release()
        self.assertEqual(self.tasks._tasks, {})

    def test_health_failure_is_reported_and_releases_lock(self):
        self.client.check_health.return_value = {"status": "error", "error": "Model unavailable"}
        with patch("src.html_ai_tasks.generate_basic_html"):
            self.tasks.start("job_offline")
            self.join("job_offline")
        self.assertEqual(self.tasks.status("job_offline")["error"], "Model unavailable")
        self.assertFalse(self.manager.ai_lock.locked())

    def test_restart_marks_persisted_running_task_interrupted(self):
        saved = dict(status="running", stage="waiting_ai", started_at=1, updated_at=2,
                     stage_started_at=2, job_id="job_interrupted")
        with patch("builtins.open", mock_open(read_data=json.dumps(saved))):
            state = self.tasks.status("job_interrupted")
        self.assertEqual(state["status"], "failed")
        self.assertIn("Server restarted", state["error"])

    def test_api_start_status_and_cancel(self):
        from fastapi.testclient import TestClient
        from src.server import app
        api_tasks = Mock()
        api_tasks.start.return_value = {"status": "running"}
        api_tasks.status.return_value = {"status": "running", "completed_chunks": 3}
        api_tasks.cancel.return_value = {"status": "cancelling"}
        with patch("src.server.db.get_job_status", return_value=object()), \
                patch("src.server.html_ai_tasks", api_tasks):
            client = TestClient(app)
            base = "/api/jobs/job_progress/export/html/ai"
            self.assertEqual(client.post(base + "/start").status_code, 202)
            res = client.get(base + "/progress")
            self.assertEqual(res.json()["completed_chunks"], 3)
            self.assertEqual(res.headers["cache-control"], "no-store")
            self.assertEqual(client.post(base + "/cancel").json()["status"], "cancelling")


if __name__ == "__main__":
    unittest.main()
