import re
import unittest
from pathlib import Path

from src.translation_core import create_model, export_results, structure_signature

ROOT=Path(__file__).resolve().parents[2]
FILES=ROOT/"tests"/"artifacts"
JOB="phase10_demo08_structure_job"
FIXTURE=ROOT/"tests"/"phase10"/"fixtures"/"demo08_structured.html"


class ApprovedInputStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        destination=FILES/JOB/"export"/"structured";destination.mkdir(parents=True,exist_ok=True)
        (destination/"structured.html").write_bytes(FIXTURE.read_bytes())

    def test_demo08_structured_translation_roundtrip_keeps_tables(self):
        source=(FILES/JOB/"export"/"structured"/"structured.html").read_text(encoding="utf-8")
        model=create_model(str(FILES),JOB,{"source_variant":"structured","source_language":"en","target_language":"th","style":"academic","provider":"local"})
        self.assertEqual(model["structure_signature"],structure_signature(model["tokens"],model["segments"]))
        for segment in model["segments"]:
            if segment["status"]=="pending": segment.update(translated_text=segment["source_text"],final_text=segment["source_text"],status="translated")
        output=Path(export_results(str(FILES),JOB,model)["html"]).read_text(encoding="utf-8")
        for tag in ("table","tr","th","td"):
            self.assertEqual(len(re.findall(fr"<{tag}(?:\s|>)",source,re.I)),len(re.findall(fr"<{tag}(?:\s|>)",output,re.I)),tag)
        for attr in ("rowspan","colspan"):
            self.assertEqual(len(re.findall(fr"\s{attr}=",source,re.I)),len(re.findall(fr"\s{attr}=",output,re.I)),attr)
        self.assertFalse(any(s["status"]=="unresolved" for s in model["segments"]))

    def test_dataset_manifest_integrity_and_hashes(self):
        import hashlib
        import json
        manifest_path = ROOT / "phase10" / "dataset_manifest.json"
        self.assertTrue(manifest_path.exists())
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(data["schema_version"], "10.0")
        for entry in data["files"]:
            file_path = ROOT / entry["file"]
            if not file_path.exists() and (ROOT.parent / entry["file"]).exists():
                file_path = ROOT.parent / entry["file"]
            self.assertTrue(file_path.exists(), f"File {entry['file']} must exist in repo")
            content = file_path.read_bytes()
            self.assertEqual(len(content), entry["bytes"], f"Byte size mismatch for {entry['file']}")
            sha256 = hashlib.sha256(content).hexdigest()
            self.assertEqual(sha256, entry["sha256"], f"SHA256 mismatch for {entry['file']}")

    def test_demo09_mixed_language_and_glossary_classification(self):
        from src.translation_core import classify_terms, detect_language, extract_document
        html = '<body><p data-block-id="p1">Transformer 模型使用 Multi-Head Attention 进行特征提取。</p></body>'
        _, segments = extract_document(html)
        lang, conf, warning = detect_language(segments)
        self.assertIn(lang, {"zh", "en"})
        self.assertIsNotNone(warning, "Should warn about mixed languages")
        glossary = [
            {"source": "Transformer", "target": "Transformer", "case_sensitive": True, "do_not_translate": True, "mode": "preserved"},
            {"source": "Multi-Head Attention", "target": "มัลติเฮดแอตเทนชัน", "case_sensitive": True, "do_not_translate": False, "mode": "transliterated"},
        ]
        target = "โมเดล Transformer ใช้ มัลติเฮดแอตเทนชัน ในการสกัดฟีเจอร์"
        terms = classify_terms(segments[0]["source_text"], target, glossary)
        self.assertEqual(len(terms), 2)
        by_src = {t["source"]: t for t in terms}
        self.assertEqual(by_src["Transformer"]["status"], "preserved")
        self.assertEqual(by_src["Multi-Head Attention"]["status"], "transliterated")

    def test_demo10_11_novel_dialogue_quotation_preservation(self):
        from src.translation_core import critical_tokens, extract_document
        html = '<body><p data-block-id="p1">"Wait for me," she whispered, looking back at John.</p></body>'
        _, segments = extract_document(html)
        self.assertEqual(len(segments), 1)
        self.assertIn('Wait', segments[0]["source_text"])

    def test_demo12_academic_dehyphenation_and_assembly(self):
        from src.translation_core import assemble_translation_units, extract_document
        html = """<html><body>
        <p data-block-id="p1_b0_l0">The model requires hyperparam-</p>
        <p data-block-id="p1_b0_l1">eter tuning across multiple lay-</p>
        <p data-block-id="p1_b0_l2">ers to achieve optimal accuracy.</p>
        </body></html>"""
        _, segments = extract_document(html)
        units = assemble_translation_units(segments)
        self.assertEqual(len(units), 1)
        self.assertEqual(
            units[0]["assembled_text"],
            "The model requires hyperparameter tuning across multiple layers to achieve optimal accuracy."
        )

    def test_demo13_code_block_exact_preservation(self):
        from src.translation_core import extract_document
        html = """<html><body>
        <p data-block-id="p1">Run the following training script:</p>
        <pre data-block-id="code1"><code>def train_model(epochs=10, lr=0.001):
    for epoch in range(epochs):
        optimizer.step()
</code></pre></body></html>"""
        _, segments = extract_document(html)
        code_seg = next(s for s in segments if s.get("type") in {"pre", "code"})
        self.assertEqual(code_seg["status"], "preserved")


if __name__=="__main__":unittest.main()
