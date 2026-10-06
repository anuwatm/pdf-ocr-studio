"""AI HTML batching regressions with in-memory inputs and no filesystem writes."""
import json
import re
import unittest
from contextlib import ExitStack
from unittest.mock import Mock, mock_open, patch

from src.html_exporter import generate_ai_html


class AiHtmlBatchTests(unittest.TestCase):
    def run_export(self, client, count=60, text="ข้อความภาษาไทย " * 10, **options):
        self.source = "<html><body>" + "".join(
            f'<p data-page="1">{text}{i}</p>' for i in range(count)
        ) + "</body></html>"
        with ExitStack() as stack:
            stack.enter_context(patch("src.html_exporter.os.path.exists", return_value=True))
            stack.enter_context(patch("builtins.open", mock_open(read_data=self.source)))
            stack.enter_context(patch("src.html_exporter.compute_source_revision", return_value="revision"))
            self.write = stack.enter_context(patch("src.html_exporter.atomic_write_text"))
            self.meta_write = stack.enter_context(patch("src.html_exporter._update_export_meta"))
            return generate_ai_html("job_batches", llm_client=client, **options)

    @staticmethod
    def units(prompt):
        return json.loads(prompt.split("Units to classify:\n", 1)[1])

    def good_client(self):
        client = Mock(spec=["generate", "model"])
        client.model = "test-model"
        client.generate.side_effect = lambda **kw: json.dumps([
            {"unit": unit["unit"], "tag": "p"} for unit in self.units(kw["prompt"])
        ])
        return client

    def test_100_page_sized_input_is_bounded_and_every_unit_preserved(self):
        client = self.good_client()
        content, meta = self.run_export(client, count=2360)
        prompts = [call.kwargs["prompt"] for call in client.generate.call_args_list]
        self.assertGreater(len(prompts), 95)
        self.assertTrue(all(len(p.encode("utf-8")) <= 5500 for p in prompts))
        self.assertTrue(all(len(self.units(p)) <= 25 for p in prompts))
        ids = [u["unit"] for p in prompts for u in self.units(p)]
        self.assertEqual(ids, [f"u{i}" for i in range(2360)])
        self.assertEqual(meta["chunk_count"], len(prompts))
        self.assertEqual(meta["completed_chunks"], len(prompts))
        self.assertEqual(meta["validator_status"], "passed")
        self.assertEqual(re.sub("<[^>]+>", "", content), re.sub("<[^>]+>", "", self.source))
        self.write.assert_called_once()

    def test_global_heading_rules_checked_across_batches(self):
        client = self.good_client()
        def response(**kw):
            units = self.units(kw["prompt"])
            return json.dumps([{"unit": u["unit"], "tag": "h1" if i == 0 else "p"}
                               for i, u in enumerate(units)])
        client.generate.side_effect = response
        content, meta = self.run_export(client)
        self.assertEqual(meta["validator_status"], "rejected")
        self.assertIn("Multiple h1", meta["validator_reason"])
        self.assertEqual(content, self.source)
        self.write.assert_not_called()
        self.assertIn("h1 already used: true", client.generate.call_args_list[1].kwargs["prompt"])

    def test_later_batch_failure_never_publishes_partial_html(self):
        client = self.good_client()
        good_response = client.generate.side_effect
        calls = 0
        def response(**kw):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("Timeout after 90s")
            return good_response(**kw)
        client.generate.side_effect = response
        content, meta = self.run_export(client)
        self.assertEqual(content, self.source)
        self.assertEqual(meta["failed_chunk"], 2)
        self.assertEqual(meta["completed_chunks"], 1)
        self.assertEqual(meta["error"], "Timeout after 90s")
        self.write.assert_not_called()

    def test_missing_or_cross_batch_units_rejected(self):
        client = self.good_client()
        client.generate.side_effect = lambda **kw: json.dumps([
            {"unit": self.units(kw["prompt"])[0]["unit"], "tag": "p"}])
        _, meta = self.run_export(client)
        self.assertEqual(meta["validator_status"], "rejected")
        self.assertIn("every unit", meta["validator_reason"])
        self.write.assert_not_called()

    def test_example_json_before_actual_answer_does_not_break_parser(self):
        client = self.good_client()
        good_response = client.generate.side_effect
        client.generate.side_effect = lambda **kw: (
            '[{"unit":"example","tag":"p"}]\nActual answer:\n```json\n'
            + good_response(**kw) + '\n```')
        _, meta = self.run_export(client)
        self.assertEqual(meta["validator_status"], "passed")

    def test_repeated_json_from_live_model_is_accepted(self):
        client = self.good_client()
        good_response = client.generate.side_effect
        client.generate.side_effect = lambda **kw: (
            good_response(**kw) + '```json\n' + good_response(**kw) + '\n```')
        _, meta = self.run_export(client)
        self.assertEqual(meta["validator_status"], "passed")

    def test_heading_jump_between_batches_rejected(self):
        client = self.good_client()
        calls = 0
        def response(**kw):
            nonlocal calls
            calls += 1
            return json.dumps([{"unit": u["unit"], "tag": (
                "h1" if calls == 1 and i == 0 else "h3" if calls == 2 and i == 0 else "p")}
                for i, u in enumerate(self.units(kw["prompt"]))])
        client.generate.side_effect = response
        _, meta = self.run_export(client)
        self.assertEqual(meta["validator_status"], "rejected")
        self.assertIn("jumped", meta["validator_reason"])
        self.write.assert_not_called()

    def test_progress_counts_real_batches_and_cancel_does_not_publish(self):
        client = self.good_client()
        events = []
        _, meta = self.run_export(client, progress_callback=lambda **event: events.append(event))
        waiting = [event for event in events if event["stage"] == "waiting_ai"]
        self.assertEqual(len(waiting), meta["chunk_count"])
        self.assertEqual([e["completed_chunks"] for e in waiting], list(range(len(waiting))))
        self.assertEqual(events[-1]["stage"], "publishing")
        self.assertEqual(events[-1]["completed_chunks"], meta["chunk_count"])
        cancelled = False
        good_response = client.generate.side_effect
        def response(**kw):
            nonlocal cancelled
            cancelled = True
            return good_response(**kw)
        client.generate.side_effect = response
        _, meta = self.run_export(client, cancel_requested=lambda: cancelled)
        self.assertEqual(meta["validator_status"], "cancelled")
        self.write.assert_not_called()

    def test_api_reports_applied_and_offline_reason(self):
        from fastapi.testclient import TestClient
        from src.server import app
        client = TestClient(app)
        manager = Mock()
        manager.is_ai_in_use.return_value = False
        manager.ai_lock.acquire.return_value = True
        llm = Mock()
        llm.model = "test-model"
        llm.check_health.return_value = {"status": "connected"}
        with patch("src.server.db.get_job_status", return_value=object()), \
                patch("src.server.job_manager", manager), \
                patch("src.llm_client.LocalLLMClient", return_value=llm), \
                patch("src.html_exporter.generate_ai_html", return_value=("html", {"validator_status": "passed"})):
            response = client.post("/api/jobs/job_batches/export/html", json={"mode": "ai"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ai_applied"])
        llm.check_health.return_value = {"status": "model_not_found", "error": "Model test-model not found"}
        with patch("src.server.db.get_job_status", return_value=object()), \
                patch("src.server.job_manager", manager), \
                patch("src.llm_client.LocalLLMClient", return_value=llm), \
                patch("src.html_exporter.generate_basic_html", return_value=("html", {"source_revision": "rev"})), \
                patch("src.html_exporter._update_export_meta"):
            response = client.post("/api/jobs/job_batches/export/html", json={"mode": "ai"})
        self.assertFalse(response.json()["ai_applied"])
        self.assertEqual(response.json()["meta"]["message"], "Model test-model not found")


if __name__ == "__main__":
    unittest.main()
