"""Tests the Local LLM configuration page APIs without changing the real .env file."""
import json
import tempfile
import subprocess
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from src import config
from src.server import app
from src.llm_client import LocalLLMClient


class TestLocalLLMConfig(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_01_config_page_and_read_api_hide_secret(self):
        page = self.client.get("/config.html")
        self.assertEqual(page.status_code, 200)
        self.assertIn("ตั้งค่า Local LLM", page.text)

        response = self.client.get("/api/ai/config")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("api_key_configured", data)
        self.assertIn(data["transport"], {"api", "cli"})
        self.assertNotIn("api_key", data)

    def test_02_rejects_non_local_endpoint(self):
        response = self.client.post(
            "/api/ai/config/test",
            json={"base_url": "http://example.com/v1", "model": "external", "timeout": 60},
        )
        self.assertEqual(response.status_code, 400)

    def test_03_save_updates_runtime_and_temp_env(self):
        old_path = config.ENV_PATH
        old_values = (config.LLM_BASE_URL, config.LLM_MODEL, config.LLM_TIMEOUT, config.LLM_API_KEY, config.LLM_TRANSPORT, config.LLM_CLI_PROVIDER)
        try:
            with tempfile.TemporaryDirectory() as directory:
                config.ENV_PATH = Path(directory) / ".env"
                response = self.client.put(
                    "/api/ai/config",
                    json={
                        "base_url": "http://127.0.0.1:1234/v1",
                        "model": "test-local-model",
                        "timeout": 45,
                        "api_key": "test-secret",
                        "transport": "api",
                        "cli_provider": "agy",
                    },
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["model"], "test-local-model")
                self.assertNotIn("api_key", response.json())
                saved = config.ENV_PATH.read_text(encoding="utf-8")
                self.assertIn("LLM_MODEL=test-local-model", saved)
                self.assertIn("LLM_API_KEY=test-secret", saved)
                self.assertIn("LLM_TRANSPORT=api", saved)
                self.assertIn("LLM_CLI_PROVIDER=agy", saved)
        finally:
            config.ENV_PATH = old_path
            config.LLM_BASE_URL, config.LLM_MODEL, config.LLM_TIMEOUT, config.LLM_API_KEY, config.LLM_TRANSPORT, config.LLM_CLI_PROVIDER = old_values

    @patch.object(LocalLLMClient,"_resolve_lms_cli",return_value=r"C:\Tools\lms.exe")
    @patch("src.llm_client.subprocess.run")
    def test_04_cli_adapter_uses_fixed_lms_command_without_catalog_download(self,run,resolve):
        run.side_effect=[
            Mock(returncode=0,stdout='{"models":[{"key":"google/gemma-4-e2b"}]}',stderr=""),
            Mock(returncode=0,stdout="ผลลัพธ์ภาษาไทย",stderr=""),
        ]
        client=LocalLLMClient(transport="cli",cli_provider="lms",model="google/gemma-4-e2b",timeout=30)
        self.assertEqual(client.check_health()["status"],"connected")
        self.assertEqual(client.generate("Translate this"),"ผลลัพธ์ภาษาไทย")
        command=run.call_args_list[1].args[0]
        self.assertEqual(command[0],r"C:\Tools\lms.exe")
        self.assertIn("--dont-fetch-catalog",command)
        self.assertIn("--reasoning",command)
        self.assertFalse(any(token in command for token in ("cmd","powershell","gemini","codex")))

    @patch("src.cli_status.subprocess.run")
    @patch("src.cli_status.shutil.which")
    def test_05_cli_status_reports_primary_adapters_without_shell(self, which, run):
        which.side_effect = lambda command: rf"C:\Tools\{command}.exe"

        def result(command, **kwargs):
            joined = " ".join(command).lower()
            if "codex.exe --version" in joined:
                return subprocess.CompletedProcess(command, 0, "codex-cli 0.150.1\n", "")
            if "codex.exe login status" in joined:
                return subprocess.CompletedProcess(command, 0, "Logged in using ChatGPT\n", "")
            if "gemini.exe --version" in joined:
                return subprocess.CompletedProcess(command, 0, "0.41.2\n", "")
            if "gemini.exe gemma status" in joined:
                return subprocess.CompletedProcess(command, 1, "Binary: Not installed\n", "")
            return subprocess.CompletedProcess(command, 0, "CLI commit: test\n", "")

        run.side_effect = result
        with tempfile.TemporaryDirectory() as directory,patch("src.cli_status.STATUS_PATH",Path(directory)/"status.json"):
            cached = self.client.get("/api/ai/cli/status")
            self.assertEqual(cached.status_code, 200);self.assertIsNone(cached.json()["checked_at"])
            self.assertEqual(run.call_count,0)
            response = self.client.post("/api/ai/cli/status/check")
            self.assertEqual(response.status_code, 200)
            adapters = {item["id"]: item for item in response.json()["adapters"]}
            calls_after_check=run.call_count
            persisted=self.client.get("/api/ai/cli/status").json()
            self.assertEqual(persisted["checked_at"],response.json()["checked_at"])
            self.assertEqual(run.call_count,calls_after_check)
        self.assertEqual(set(adapters), {"codex", "gemini", "agy", "claude", "lms"})
        self.assertTrue(adapters["codex"]["primary"])
        self.assertEqual(adapters["codex"]["authentication"], "ready")
        self.assertTrue(adapters["gemini"]["primary"])
        self.assertEqual(adapters["gemini"]["local_runtime"], "not_ready")
        self.assertTrue(adapters["agy"]["primary"])
        self.assertEqual(adapters["agy"]["authentication"], "check_on_use")
        self.assertTrue(adapters["claude"]["primary"])
        self.assertEqual(adapters["claude"]["authentication"], "check_on_use")
        self.assertFalse(adapters["lms"]["primary"])
        self.assertTrue(all(call.kwargs["shell"] is False for call in run.call_args_list))

    @patch.object(LocalLLMClient, "_resolve_cli", return_value=r"C:\Tools\ai.exe")
    @patch("src.llm_client.subprocess.run")
    def test_06_primary_cli_adapters_use_stdin_and_safe_modes(self, run, resolve):
        cases = {
            "codex": "ผลลัพธ์",
            "gemini": '{"response":"ผลลัพธ์"}',
            "agy": '{"event":"result","result":{"status":"SUCCESS","response":"{\\\"response\\\":\\\"ผลลัพธ์\\\"}"}}',
            "claude": '{"result":"ผลลัพธ์"}',
        }
        for provider, stdout in cases.items():
            with self.subTest(provider=provider):
                run.reset_mock()
                run.return_value = Mock(returncode=0, stdout=stdout, stderr="")
                client = LocalLLMClient(transport="cli", cli_provider=provider, model="test-model", timeout=30)
                self.assertEqual(client.generate("แปลข้อความ"), "ผลลัพธ์")
                command = run.call_args.args[0]
                self.assertEqual(run.call_args.kwargs["shell"], False)
                self.assertIn("แปลข้อความ", run.call_args.kwargs["input"])
                self.assertNotIn("--yolo", command)
                self.assertNotIn("--dangerously-skip-permissions", command)
                if provider == "codex":
                    self.assertIn("read-only", command)
                    self.assertIn("--ephemeral", command)
                elif provider == "gemini":
                    self.assertIn("plan", command)
                    self.assertIn("--output-format", command)
                elif provider == "agy":
                    self.assertIn("--disable-slash-commands", command)
                    self.assertIn("plan", command)
                    self.assertIn("stream-json", command)
                    self.assertFalse(any(item.startswith("--print=") for item in command))
                    self.assertNotIn("แปลข้อความ", " ".join(command))
                    self.assertEqual(json.loads(run.call_args.kwargs["input"])["event"], "user")
                else:
                    self.assertIn("--permission-mode", command)
                    self.assertIn("--max-turns", command)
                    self.assertIn("--disallowedTools", command)
                    self.assertIn("WebSearch", command)

    def test_07_cli_json_envelope_unwraps_nested_translation_payload(self):
        wrapped = json.dumps({
            "result": {
                "message": {
                    "content": [{"text": json.dumps({"segments": [{"id": "seg-1", "text": "คำแปล"}]})}]
                }
            }
        }, ensure_ascii=False)
        output = LocalLLMClient._extract_cli_json_output(wrapped)
        self.assertEqual(json.loads(output)["segments"][0], {"id": "seg-1", "text": "คำแปล"})

    def test_08_cli_json_output_strips_thinking_and_markdown_fence(self):
        wrapped = json.dumps({"response": "<thought>ignore this</thought>\n```json\n{\"segments\":[{\"id\":\"seg-1\",\"text\":\"คำแปล\"}]}\n```"}, ensure_ascii=False)
        output = LocalLLMClient._extract_cli_json_output(wrapped)
        self.assertEqual(json.loads(output)["segments"][0]["text"], "คำแปล")


if __name__ == "__main__":
    unittest.main()
