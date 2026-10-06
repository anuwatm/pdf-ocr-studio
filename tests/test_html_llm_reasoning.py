"""Per-request HTML thinking control; preserve existing OpenAI-compatible behavior."""
import io
import json
import unittest
import urllib.error
from unittest.mock import Mock, patch

from src.llm_client import LocalLLMClient


class HtmlLlmReasoningTests(unittest.TestCase):
    def client(self):
        with patch("src.llm_client.OpenAI"):
            return LocalLLMClient(base_url="http://127.0.0.1:1234/v1",
                                  model="test-model", timeout=90)

    def models(self, allowed=("off", "on")):
        return io.BytesIO(json.dumps({"models": [{"key": "test-model", "capabilities": {
            "reasoning": {"allowed_options": list(allowed)}}}]}).encode())

    def result(self):
        return io.BytesIO(json.dumps({"output": [
            {"type": "reasoning", "content": "must not become annotations"},
            {"type": "message", "content": '[{"unit":"u0","tag":"p"}]'}]}).encode())

    def test_supported_model_disables_thinking_only_for_html(self):
        client = self.client()
        with patch("src.llm_client.urllib.request.urlopen", side_effect=[self.models(), self.result()]) as request:
            content = client.generate_html_annotations("prompt", max_tokens=1600)
        body = json.loads(request.call_args_list[1].args[0].data)
        self.assertEqual(body["reasoning"], "off")
        self.assertFalse(body["store"])
        self.assertEqual(body["max_output_tokens"], 1600)
        self.assertEqual(content, '[{"unit":"u0","tag":"p"}]')
        client._client.chat.completions.create.assert_not_called()

    def test_other_servers_keep_compatible_generate(self):
        client = self.client()
        client.generate = Mock(return_value="compatible response")
        with patch("src.llm_client.urllib.request.urlopen", side_effect=urllib.error.URLError("unsupported")):
            self.assertEqual(client.generate_html_annotations("prompt"), "compatible response")
        client.generate.assert_called_once_with(prompt="prompt", temperature=0.0, max_tokens=1600)

    def test_no_off_capability_keeps_compatible_generate(self):
        client = self.client()
        client.generate = Mock(return_value="fallback")
        with patch("src.llm_client.urllib.request.urlopen", return_value=self.models(("on",))):
            self.assertEqual(client.generate_html_annotations("prompt"), "fallback")

    def test_timeout_is_precise_and_does_not_retry_thinking_request(self):
        client = self.client()
        with patch("src.llm_client.urllib.request.urlopen", side_effect=[self.models(), TimeoutError()]):
            with self.assertRaisesRegex(RuntimeError, "Timeout after 90s"):
                client.generate_html_annotations("prompt")

    def test_capability_lookup_cached_between_batches(self):
        client = self.client()
        with patch("src.llm_client.urllib.request.urlopen", side_effect=[self.models(), self.result(), self.result()]) as request:
            client.generate_html_annotations("first")
            client.generate_html_annotations("second")
        self.assertEqual(request.call_count, 3)


if __name__ == "__main__":
    unittest.main()
