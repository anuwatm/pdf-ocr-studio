import json
import os
import unittest
from pathlib import Path

from src.translation_core import (assemble_translation_units, batch_segments, classify_terms, create_model, critical_tokens, extract_document,
    load_glossary, looks_like_code, render_html, save_glossary, save_model, translation_revision,
    structure_signature, validate_config, validate_translation)

ROOT = Path(__file__).resolve().parents[2]
FILES = ROOT / "tests" / "artifacts"
JOB = "phase10_core_job"
JOB_DIR = FILES / JOB

SOURCE = """<!doctype html><html lang="en"><head><title>Guide</title></head><body>
<h1 id="intro">API Guide 2026</h1><table data-page="1"><tbody><tr>
<td data-cell-id="c1">Price: $20.00</td><td data-cell-id="c2">OpenAI API v3</td>
</tr></tbody></table><p data-block-id="b1">Visit https://example.com at 10:30.</p>
</body></html>"""


class TranslationCoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (JOB_DIR / "export").mkdir(parents=True, exist_ok=True)
        (JOB_DIR / "export" / "final.html").write_text(SOURCE, encoding="utf-8")
        (JOB_DIR / "final.txt").write_text("First paragraph & API\nline two\n\nSecond <paragraph>\fPage two", encoding="utf-8")

    def test_01_config_bcp47_and_same_language_guard(self):
        config = validate_config({"source_language":"en","target_language":"th","style":"academic","provider":"local"})
        self.assertEqual(config["target_language"], "th")
        with self.assertRaisesRegex(ValueError, "different"):
            validate_config({"source_language":"th","target_language":"th","style":"general","provider":"local"})

    def test_02_stable_segments_and_structure_roundtrip(self):
        tokens, segments = extract_document(SOURCE)
        self.assertEqual([s["id"] for s in segments], ["seg-intro-1","seg-c1-1","seg-c2-1","seg-b1-1"])
        for segment in segments:
            segment["translated_text"] = segment["final_text"] = "แปล " + segment["source_text"]
            segment["status"] = "translated"
        output = render_html(tokens, segments)
        self.assertEqual(output.count("<td"), SOURCE.count("<td"))
        self.assertIn('data-cell-id="c1"', output)
        self.assertIn('id="intro"', output)

    def test_03_glossary_revision_conflict_and_validation(self):
        first = save_glossary(str(FILES), JOB, [
            {"source":"OpenAI API","target":"OpenAI API","do_not_translate":True,"case_sensitive":True}
        ])
        loaded = load_glossary(str(FILES), JOB)
        self.assertEqual(first["revision"], loaded["revision"])
        with self.assertRaisesRegex(ValueError, "Conflict"):
            save_glossary(str(FILES), JOB, [], "stale-revision")
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            save_glossary(str(FILES), JOB, [{"source":"API","target":"เอพีไอ"},{"source":"api","target":"API"}])
        with self.assertRaisesRegex(ValueError,"target language mismatch"):
            save_glossary(str(FILES),JOB,[{"source":"hello","target":"bonjour"}],source_language="en",target_language="th")

    def test_04_critical_token_validator(self):
        source = "Price $20.00, 50%, mail a@example.com and https://example.com [12]"
        self.assertFalse(validate_translation(source, source, []))
        warnings = validate_translation(source, "ราคา 20 ติดต่อเรา", [])
        self.assertTrue(any("critical_money" in warning for warning in warnings))
        self.assertTrue(critical_tokens(source)["email"])
        self.assertEqual(critical_tokens("Chapter 1, then 1,000 items")["number"],["1","1,000"])
        self.assertNotIn("i.e",critical_tokens("inputs (i.e., neurons)")["code"])
        self.assertIn("target_language_mismatch",validate_translation(
            "This explanatory sentence must be translated.",
            "This explanatory sentence must be translated.",[],"th"))
        self.assertNotIn("target_language_mismatch",validate_translation(
            "This explanatory sentence must be translated.",
            "ประโยคอธิบายนี้ต้องได้รับการแปล",[],"th"))

    def test_05_model_and_revision_are_deterministic(self):
        config={"source_variant":"final","source_language":"en","target_language":"th","style":"academic","provider":"local"}
        a=create_model(str(FILES),JOB,config); b=create_model(str(FILES),JOB,config)
        self.assertEqual(a["source_revision"],b["source_revision"])
        self.assertEqual(a["translation_revision"],b["translation_revision"])
        self.assertEqual(a["assembler_version"], "10.2.0")
        self.assertLessEqual(max(sum(len(s["source_text"]) for s in batch) for batch in batch_segments(a["segments"])),5000)
        self.assertLessEqual(max(len(batch) for batch in batch_segments(a["segments"])),8)
        save_model(str(FILES),JOB,a)
        saved=json.loads((JOB_DIR/"export"/"translation"/"translation.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["schema_version"],"10.0")

    def test_06_table_span_unicode_and_missing_cell_model(self):
        source='''<!doctype html><html><body><table><tr><th data-cell-id="h" colspan="2">หัวข้อ 📚</th></tr><tr><td data-cell-id="a" rowspan="2">مَرْحَبًا</td><td>unsafe cell</td></tr></table><pre>const x = 1;</pre></body></html>'''
        tokens,segments=extract_document(source)
        unresolved=next(s for s in segments if s["source_text"]=="unsafe cell")
        self.assertEqual(unresolved["status"],"unresolved")
        self.assertIn("table_cell_model_missing",unresolved["warnings"])
        self.assertNotIn(unresolved,[s for batch in batch_segments(segments) for s in batch])
        code=next(s for s in segments if "const x" in s["source_text"])
        self.assertEqual(code["status"],"preserved")
        rendered=render_html(tokens,segments)
        self.assertIn('colspan="2"',rendered);self.assertIn('rowspan="2"',rendered)
        self.assertIn("หัวข้อ 📚",rendered);self.assertIn("مَرْحَبًا",rendered)
        self.assertEqual(structure_signature(tokens,segments),structure_signature(tokens,segments))
        self.assertFalse(looks_like_code("function is code that executes on each neuron"))
        self.assertTrue(looks_like_code("function activate(value) { return value; }"))

    def test_07_units_dates_and_manual_strategy(self):
        source="2026-10-09 10:30 costs ฿250 at 5 km, ref [7]"
        warnings=validate_translation(source,"changed",[])
        for kind in ("date","time","money","unit","citation"):
            self.assertTrue(any(f"critical_{kind}" in warning for warning in warnings),kind)
        self.assertEqual(validate_config({"target_language":"th","manual_strategy":"reset"})["manual_strategy"],"reset")

    def test_08_table_row_batch_and_term_states(self):
        source='''<html><body><table><tr><td data-cell-id="a">123456</td><td data-cell-id="b">abcdef</td></tr></table><p data-block-id="p">tail</p></body></html>'''
        _,segments=extract_document(source);batches=batch_segments(segments,max_codepoints=8)
        row_ids={s["id"] for s in segments if s.get("group_id")}
        self.assertTrue(any(row_ids.issubset({s["id"] for s in batch}) for batch in batches))
        glossary=[{"source":"API","target":"เอพีไอ","case_sensitive":True,"do_not_translate":False,"mode":"transliterated"}]
        self.assertEqual(classify_terms("API","เอพีไอ",glossary)[0]["status"],"transliterated")

    def test_09_text_artifact_uses_same_stable_segment_pipeline(self):
        model=create_model(str(FILES),JOB,{"source_variant":"text_final","source_language":"en",
            "target_language":"th","style":"general","provider":"local_api"})
        self.assertEqual(model["source_format"],"text")
        self.assertEqual(model["source_variant"],"text_final")
        self.assertEqual([s["page"] for s in model["segments"]],["1","1","2"])
        self.assertEqual(model["segments"][0]["source_text"],"First paragraph & API\nline two")
        rendered=render_html(model["tokens"],model["segments"])
        self.assertIn("First paragraph &amp; API",rendered)
        self.assertIn("Second &lt;paragraph&gt;",rendered)

    def test_10_all_explicit_ai_providers_validate(self):
        for provider in ("local_api","cli_codex","cli_gemini","cli_agy","cli_claude","cli_lms"):
            self.assertEqual(validate_config({"target_language":"th","provider":provider})["provider"],provider)

    def test_11_semantic_units_keep_original_segments_and_dehyphenate_context(self):
        _, segments = extract_document('''<html><body><p data-block-id="p1_b0_l0">Multi-</p><p data-block-id="p1_b0_l1">layer networks learn.</p><p data-block-id="p1_b1_l0">New paragraph.</p></body></html>''')
        units = assemble_translation_units(segments)
        self.assertEqual(len(units), 2)
        self.assertEqual(units[0]["text"], "Multilayer networks learn.")
        self.assertEqual(units[0]["member_ids"], [segments[0]["id"], segments[1]["id"]])
        self.assertEqual(units[0]["transformations"][0]["kind"], "dehyphenate")
        self.assertEqual(segments[1]["translation_unit_member_index"], 1)
        self.assertEqual(segments[1]["translation_unit_source_span"]["segment_id"], segments[1]["id"])
        batches = batch_segments(segments, max_segments=1)
        self.assertEqual([item["id"] for item in batches[0]], units[0]["member_ids"])


if __name__ == "__main__": unittest.main()
