# Phase 8.1 — Implementation evidence

สถานะ: **IMPLEMENTATION COMPLETE / รอเจ้าของงานยืนยัน ground truth ด้วยคน**  
วันที่: 2026-10-06

## ผลส่งมอบ

- layout schema `1.0.0`: page/block/cell ID, paragraph, heading, list, table, bbox, source, confidence, evidence และ fallback งานเก่า
- PDF vector table จับคู่ข้อความ OneOCR ด้วยตำแหน่งจริง; ภาพสแกนใช้ pixel projection ตรวจเส้นและเซลล์โดยแยก provenance
- เก็บ `raw` / `corrected` / `final` แยกกัน; structured revision เปลี่ยนเมื่อข้อความต้นทางเปลี่ยน
- Text รักษา tab/เซลล์ว่าง; HTML ใช้ semantic table/list; HTML AI sanitizer และ prompt รักษา table/list
- EPUB รับ source `structured`; ตารางคงอยู่ใน XHTML และ stale guard บล็อก package เมื่อ source เปลี่ยน
- UI เทียบต้นฉบับกับ Structured HTML/OCR raw/corrected/final มีเลือกหน้า ซูม bbox, download, unresolved, mobile และ keyboard

## Regression และ browser

- Source suite: `12/12 PASS`
- Publish standalone suite: `12/12 PASS`
- Chrome และ Edge: Structured HTML/raw/corrected/final, ซูม/เลือก cell, keyboard/mobile, download และ stale ผ่าน
- Network ออกนอก loopback: `0`; console error: `0`

คำสั่ง:

```text
publish\venv\Scripts\python.exe -m unittest discover -s tests\phase8_1 -p "test_*.py" -v
publish\venv\Scripts\python.exe -m tests.phase8_1.approved_audit
publish\venv\Scripts\python.exe -m tests.phase8_1.benchmark
publish\venv\Scripts\python.exe -m tests.phase8_1.approved_epub
java -jar tools\epubcheck\epubcheck-5.3.0\epubcheck.jar phase8_1\approved_structured.epub --json phase8_1\epubcheck-structured.json
publish\venv\Scripts\python.exe -m tests.phase8_1.reader_acceptance
```

## ชุดข้อมูลอนุมัติ

- `demo/04.pdf`: vector และ scanned derivative ได้ 9×4 = 36 cells; เลข 01–08 ครบ; แถว 04/05 แยกชื่อครูกับกลวิธีสอนถูกช่องตาม `ocr_cells.json`
- `demo/08.pdf`: 11 หน้า พบ 29 tables; ครอบคลุม merged cells, multi-level headers, tab-stop columns, decimals, `£` และ dash placeholders
- private-use checkbox glyph ใน `demo/08.pdf` 9 ตำแหน่งถูกบันทึก `private_use_glyph_requires_review`; ระบบไม่เดาค่า
- ชุดอนุมัติไม่มีตัวอย่าง bullet list จึงบันทึก `not covered`; regression marker/indent ใช้ fixture ระดับ unit เท่านั้น
- รายละเอียด: `approved_audit.json`; hash ของ PDF ถูกบันทึกเพื่อป้องกันชุดข้อมูลเปลี่ยน

## EPUB และประสิทธิภาพ

- `approved_structured.epub` ผ่าน validator ภายในและ EPUBCheck 5.3.0: `0 fatal / 0 error / 0 warning`
- epub.js และ Foliate บน Chrome/Edge แสดงตารางแบบ reflow; external calls `0`
- งบล็อกก่อนวัด: structured export p95 ≤ 5.0s, peak process RSS ≤ 256MB, 10 runs
- ผลล่าสุด: p50 `0.1563s`, p90 `0.4880s`, p95/max `0.6804s`, RSS `61.15MB`: `PASS`

## จุดตรวจสุดท้ายของเจ้าของงาน

- ต้องยืนยันด้วยคนว่าอักขระทุก cell ใน `demo/04.pdf` และค่าที่รองรับใน `demo/08.pdf` ตรงต้นฉบับ
- 9 private-use checkbox glyph คงสถานะ unresolved ตามจริง; ไม่บล็อกการส่งออก แต่ต้องตรวจในหน้า Structured OCR
- ใช้ `tests/artifacts/table04_20261005/comparison.html` และ `phase8_1/approved_audit.json` ตรวจรับ
