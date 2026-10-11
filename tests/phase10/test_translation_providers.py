import json
import io
import os
import sys
import types
import unittest
import urllib.error
from unittest.mock import patch

from src.translation_core import STYLE_RULES
from src.translation_providers import (GoogleTranslationProvider, LocalTranslationProvider,
    TranslationError, _parse_response, get_provider)


class FakeClient:
    model="fixture"
    def check_health(self): return {"status":"healthy"}
    def generate(self,prompt,**kwargs):
        self.prompt=prompt
        payload=json.loads(prompt.split("Segments: ",1)[1])
        return json.dumps({"segments":[{"id":row["id"],"text":row["text"]} for row in payload]},ensure_ascii=False)


class TranslationProviderTests(unittest.TestCase):
    def test_01_strict_response_ids_and_schema(self):
        self.assertEqual(_parse_response('{"segments":[{"id":"a","text":"x"}]}',["a"])[0]["text"],"x")
        for value in ('outside json', 'prefix {"segments":[{"id":"a","text":"x"}]}', '{"segments":[{"id":"b","text":"x"}]}', '{"segments":[{"id":"a"}]}'):
            with self.assertRaises(TranslationError): _parse_response(value,["a"])

    def test_02_local_prompt_styles_and_protected_tokens(self):
        for style,rule in STYLE_RULES.items():
            client=FakeClient();provider=LocalTranslationProvider(client)
            rows=provider.translate([{"id":"s1","source_text":"OpenAI costs $20 at 5 km on 2026-10-09"}],
                {"target_language":"th","style":style},
                [{"source":"OpenAI","target":"","case_sensitive":True,"do_not_translate":True}])
            self.assertIn(rule,client.prompt)
            self.assertEqual(rows[0]["text"],"OpenAI costs $20 at 5 km on 2026-10-09")

    def test_03_cloud_requires_consent_before_credentials_or_network(self):
        with self.assertRaisesRegex(TranslationError,"consent"):
            GoogleTranslationProvider().translate([],{
                "cloud_consent":False,"target_language":"th","source_language":"auto"},[])

    def test_04_google_http_error_taxonomy(self):
        google=types.ModuleType("google");auth=types.ModuleType("google.auth");transport=types.ModuleType("google.auth.transport");requests=types.ModuleType("google.auth.transport.requests")
        class Credentials:
            token="fixture-token"
            def refresh(self,request): pass
        auth.default=lambda **kwargs:(Credentials(),"fixture-project");requests.Request=object;google.auth=auth
        modules={"google":google,"google.auth":auth,"google.auth.transport":transport,"google.auth.transport.requests":requests}
        config={"cloud_consent":True,"target_language":"th","source_language":"en"};segments=[{"id":"s1","source_text":"hello world"}]
        expected={401:("auth",False),429:("quota",False),500:("transient",True)}
        with patch.dict(sys.modules,modules),patch.dict(os.environ,{"GOOGLE_CLOUD_PROJECT":"fixture-project"}):
            for status,(code,retryable) in expected.items():
                error=urllib.error.HTTPError("https://translation.googleapis.com",status,"error",{},io.BytesIO())
                with patch("urllib.request.urlopen",side_effect=error),self.assertRaises(TranslationError) as caught:
                    GoogleTranslationProvider().translate(segments,config,[])
                self.assertEqual(caught.exception.code,code);self.assertEqual(caught.exception.retryable,retryable)

    def test_05_explicit_ai_provider_routes(self):
        local=get_provider("local_api");self.assertEqual(local.client.transport,"api");self.assertFalse(local.cloud)
        expected={"cli_codex":"codex","cli_gemini":"gemini","cli_agy":"agy","cli_claude":"claude","cli_lms":"lms"}
        for provider,adapter in expected.items():
            route=get_provider(provider)
            self.assertEqual(route.client.transport,"cli");self.assertEqual(route.client.cli_provider,adapter)
        self.assertTrue(get_provider("cli_codex").cloud);self.assertFalse(get_provider("cli_lms").cloud)

    def test_06_cloud_cli_requires_consent(self):
        provider=LocalTranslationProvider(FakeClient(),name="cli_codex",cloud=True)
        with self.assertRaisesRegex(TranslationError,"consent"):
            provider.translate([{"id":"s1","source_text":"hello"}],{"target_language":"th","style":"general","cloud_consent":False},[])

    def test_07_google_credential_file_and_api_key_detection(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            f.write(json.dumps({"type": "service_account", "project_id": "auto-detected-proj"}))
            f_path = f.name
        try:
            with patch.dict(os.environ, {"GOOGLE_APPLICATION_CREDENTIALS": f_path, "GOOGLE_CLOUD_PROJECT": ""}):
                provider = GoogleTranslationProvider()
                cap = provider.capability()
                self.assertTrue(cap["available"])
                self.assertEqual(provider._settings()[0], "auto-detected-proj")
        finally:
            os.remove(f_path)

        with patch.dict(os.environ, {"GOOGLE_CLOUD_PROJECT": "", "GOOGLE_APPLICATION_CREDENTIALS": "", "GOOGLE_TRANSLATION_API_KEY": "test-key"}):
            cap = GoogleTranslationProvider().capability()
            self.assertTrue(cap["available"])

    def test_08_google_html_entity_unescaping_and_token_tolerance(self):
        google = types.ModuleType("google")
        auth = types.ModuleType("google.auth")
        transport = types.ModuleType("google.auth.transport")
        requests = types.ModuleType("google.auth.transport.requests")
        class Credentials:
            token = "fixture-token"
            def refresh(self, request): pass
        auth.default = lambda **kwargs: (Credentials(), "fixture-project")
        requests.Request = object
        google.auth = auth
        modules = {"google": google, "google.auth": auth, "google.auth.transport": transport, "google.auth.transport.requests": requests}

        fake_resp = io.BytesIO(json.dumps({
            "translations": [{"translatedText": "&quot;สวัสดี&quot; &amp; __ PHASE_TOKEN_A __"}]
        }).encode("utf-8"))

        class MockResponse:
            def __enter__(self): return fake_resp
            def __exit__(self, *args): pass

        with patch.dict(sys.modules, modules), patch.dict(os.environ, {"GOOGLE_CLOUD_PROJECT": "fixture-project"}):
            with patch("urllib.request.urlopen", return_value=MockResponse()):
                rows = GoogleTranslationProvider().translate(
                    [{"id": "s1", "source_text": '"Hello" & safe'}],
                    {"cloud_consent": True, "target_language": "th", "source_language": "en"},
                    [{"source": "safe", "target": "", "do_not_translate": True}]
                )
                self.assertEqual(rows[0]["text"], '"สวัสดี" & safe')

    def test_09_google_v3_auth_falls_back_to_configured_v2_key(self):
        google = types.ModuleType("google")
        auth = types.ModuleType("google.auth")
        transport = types.ModuleType("google.auth.transport")
        requests = types.ModuleType("google.auth.transport.requests")
        class Credentials:
            token = "fixture-token"
            def refresh(self, request): pass
        auth.default = lambda **kwargs: (Credentials(), "fixture-project")
        requests.Request = object
        google.auth = auth
        modules = {"google": google, "google.auth": auth, "google.auth.transport": transport, "google.auth.transport.requests": requests}
        class MockResponse:
            def __enter__(self): return io.BytesIO('{"data":{"translations":[{"translatedText":"สวัสดี"}]}}'.encode("utf-8"))
            def __exit__(self, *args): pass
        auth_error = urllib.error.HTTPError("https://translation.googleapis.com", 403, "forbidden", {}, io.BytesIO())
        with patch.dict(sys.modules, modules), patch.dict(os.environ, {"GOOGLE_CLOUD_PROJECT": "fixture-project", "GOOGLE_TRANSLATION_API_KEY": "test-key"}):
            with patch("urllib.request.urlopen", side_effect=[auth_error, MockResponse()]) as open_url:
                rows = GoogleTranslationProvider().translate(
                    [{"id": "s1", "source_text": "hello"}],
                    {"cloud_consent": True, "target_language": "th", "source_language": "en"}, [])
        self.assertEqual(rows, [{"id": "s1", "text": "สวัสดี"}])
        self.assertEqual(open_url.call_count, 2)


if __name__=="__main__": unittest.main()
