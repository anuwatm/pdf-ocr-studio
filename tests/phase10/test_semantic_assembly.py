import json
import os
import unittest
from unittest.mock import MagicMock, patch

from src.llm_client import (
    ALLOWED_CLI_ENV_VARS,
    MAX_CLI_OUTPUT_CHARS,
    LocalLLMClient,
    get_safe_cli_env,
)
from src.translation_core import (
    analyze_dehyphenation,
    assemble_translation_units,
    create_model,
    export_results,
    extract_document,
    render_html,
    structure_signature,
)
from src.translation_providers import (
    build_cli_protocol_envelope,
    get_provider,
    TranslationError,
)


class SemanticAssemblyTests(unittest.TestCase):
    def test_01_soft_hyphen_dehyphenation(self):
        result = analyze_dehyphenation("trans\u00ad", "lation")
        self.assertTrue(result["should_dehyphenate"])
        self.assertEqual(result["kind"], "soft_hyphen")
        self.assertEqual(result["before_part"] + result["combined_separator"] + result["after_part"], "translation")

    def test_02_eol_split_word_merge(self):
        result = analyze_dehyphenation("lay-", "ers")
        self.assertTrue(result["should_dehyphenate"])
        self.assertEqual(result["kind"], "dehyphenate")
        self.assertEqual(result["before_part"] + result["combined_separator"] + result["after_part"], "layers")

    def test_03_compound_word_preservation(self):
        # self-, well-, cross-, co-
        cases = [
            ("self-", "learning", "self-learning"),
            ("well-", "known", "well-known"),
            ("cross-", "validation", "cross-validation"),
            ("co-", "operative", "co-operative"),
        ]
        for before, after, expected in cases:
            res = analyze_dehyphenation(before, after)
            self.assertFalse(res["should_dehyphenate"], f"Should preserve compound {expected}")
            self.assertEqual(res["kind"], "compound_word")
            self.assertEqual(before + res["combined_separator"] + after, expected)

    def test_04_minus_sign_and_code_preservation(self):
        # minus sign
        minus_res = analyze_dehyphenation("val -", "10")
        self.assertFalse(minus_res["should_dehyphenate"])
        self.assertEqual(minus_res["kind"], "minus_sign")

        # URL / email
        url_res = analyze_dehyphenation("https://example.com-", "service")
        self.assertFalse(url_res["should_dehyphenate"])
        self.assertEqual(url_res["kind"], "code_or_identifier")

        # Code with underscores
        code_res = analyze_dehyphenation("param_name-", "value")
        self.assertFalse(code_res["should_dehyphenate"])
        self.assertEqual(code_res["kind"], "code_or_identifier")

        # Citation
        cite_res = analyze_dehyphenation("[12]-", "citation")
        self.assertFalse(cite_res["should_dehyphenate"])
        self.assertEqual(cite_res["kind"], "code_or_identifier")

    def test_05_capitalized_suffix_preservation(self):
        # When suffix starts with uppercase letter (sentence boundary / proper noun)
        cap_res = analyze_dehyphenation("multi-", "Layer")
        self.assertFalse(cap_res["should_dehyphenate"])
        self.assertEqual(cap_res["kind"], "capitalized_suffix")

    def test_06_assembly_and_bbox_tracking(self):
        html = """<html><body>
        <p data-block-id="p1_b0_l0" data-bbox="10,20,30,40">Deep learn-</p>
        <p data-block-id="p1_b0_l1" data-bbox="10,45,30,65">ing models</p>
        <p data-block-id="p1_b0_l2" data-bbox="10,70,30,90">scale well.</p>
        </body></html>"""
        tokens, segments = extract_document(html)
        self.assertEqual(len(segments), 3)
        self.assertEqual(segments[0]["bbox"], "10,20,30,40")

        units = assemble_translation_units(segments)
        self.assertEqual(len(units), 1)
        unit = units[0]
        self.assertEqual(unit["assembled_text"], "Deep learning models scale well.")
        self.assertEqual(len(unit["bboxes"]), 3)
        self.assertEqual(unit["bboxes"][0]["bbox"], "10,20,30,40")
        self.assertEqual(len(unit["transformations"]), 1)
        self.assertEqual(unit["transformations"][0]["kind"], "dehyphenate")

    def test_07_reversible_export_mapping_fidelity(self):
        html = """<html><body>
        <p data-block-id="p1_b0_l0">Neural net-</p>
        <p data-block-id="p1_b0_l1">works train fast.</p>
        </body></html>"""
        tokens, segments = extract_document(html)
        sig_before = structure_signature(tokens, segments)
        units = assemble_translation_units(segments)

        # Head segment receives translation, continuation segment is suppressed
        segments[0]["translated_text"] = "โครงข่ายประสาทเทียมฝึกได้เร็ว"
        segments[0]["status"] = "translated"
        segments[1]["translated_text"] = ""
        segments[1]["status"] = "translated"

        sig_after = structure_signature(tokens, segments)
        self.assertEqual(sig_before, sig_after, "Structure signature must be 100% identical")

        rendered = render_html(tokens, segments)
        self.assertIn("โครงข่ายประสาทเทียมฝึกได้เร็ว", rendered)
        self.assertIn('data-block-id="p1_b0_l0"', rendered)
        self.assertIn('data-block-id="p1_b0_l1"', rendered)

    def test_08_safe_cli_env_allowlist(self):
        with patch.dict(os.environ, {"SECRET_KEY": "supersecret", "PATH": "C:\\Windows", "SYSTEMROOT": "C:\\Windows"}):
            safe = get_safe_cli_env()
            self.assertNotIn("SECRET_KEY", safe)
            self.assertIn("PATH", safe)
            for key in safe.keys():
                self.assertIn(key, ALLOWED_CLI_ENV_VARS)

    def test_09_cli_preflight_and_envelope(self):
        # build_cli_protocol_envelope verification
        envelope = build_cli_protocol_envelope(
            [{"id": "seg-1", "source_text": "Hello"}],
            {"source_language": "en", "target_language": "th", "style": "general"},
            [],
            request_id="req-test-123"
        )
        self.assertEqual(envelope["schema_version"], "10.0")
        self.assertEqual(envelope["request_id"], "req-test-123")
        self.assertEqual(envelope["segments"][0]["id"], "seg-1")
        self.assertTrue(envelope["constraints"]["pure_json_output"])

        # preflight check for provider
        provider = get_provider("cli_codex")
        self.assertTrue(hasattr(provider, "preflight"))


if __name__ == "__main__":
    unittest.main()
