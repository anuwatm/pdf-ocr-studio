# Phase 8 Evidence — EPUB Export & XHTML Quick Preview

สถานะ: **พัฒนาเสร็จและผ่านการตรวจชุดอนุมัติ 44 หน้า; รอข้อยกเว้น fixture เพื่อปิดเกณฑ์ edge cases ทั้งหมด**
อัปเดต: 2026-10-04

## สิ่งที่ส่งมอบ

- Canonical BookModel จาก HTML parser: metadata, sections, headings, paragraphs, page provenance และ assets ใช้ชุดเดียวกันสร้าง XHTML Quick Preview กับ EPUB
- HTML ต้นทาง auto/basic/ai/final; auto เลือก final ที่ revision ปัจจุบันก่อน basic ไม่เรียก Local LLM เพิ่ม
- Metadata: title, language, identifier, creator, publisher, description และ date แบบ ISO 8601
- รูปปก PNG/JPEG แบบเลือกได้ ตรวจขนาดสูงสุด 2 MB/16 megapixels; re-encode PNG ตัด metadata; ใส่ dimensions, alt, manifest cover-image, spine และ cover landmark
- เลือกไม่มีปกหรือนำปกเดิมกลับมาใช้หลัง refresh ได้; ปก preview ส่งผ่าน loopback endpoint เท่านั้น
- สารบัญซ้อน h1–h3 และ IDs deterministic; Preview แก้ปัญหาลิงก์ fragment ใน srcdoc เพื่อไม่โหลดหน้าแอปแทนหัวข้อ
- Revision checks ก่อนและหลัง generation; package และ preview ซ้อนกันใน job เดียวตอบ 409
- สถานะ not_generated/preview_ready/generating/ready/failed/invalid/stale พร้อม last_error; รอบที่ล้มเหลวเก็บ EPUB พร้อมใช้เดิม
- Guard ร่วมกับ cleanup/delete; ดาวน์โหลดอ่าน snapshot ก่อนปล่อย lock จึงไม่ขาดกลางทางเมื่อมีการลบภายหลัง
- ZIP timestamp และ OPF modified date คงที่สำหรับ preview เดิม เพื่อสร้างซ้ำได้ deterministic
- Internal validator ตรวจ XML, container, manifest/spine, orphan resources, IDs, fragments, local references, CSS, active content, ZIP paths และขนาด
- UI มี source view, source/revision/จำนวนบท, stale warnings, ปก/metadata, keyboard และ mobile; สร้าง EPUB แล้วดาวน์โหลดอัตโนมัติ
- Source กับ publish runtime ซิงก์กัน ไม่มีการเพิ่ม EPUB renderer ลง product frontend

## หลักฐานชุดอนุมัติจริง

ใช้ผล OCR ที่มี provenance ของ demo/01.pdf–04.pdf, demo/01.png–02.png รวม 44 หน้า ตรวจ hash ของ demo ทั้ง 6 ไฟล์ตรง manifest เดิม ไม่ใช้ synthetic document แทน

- `fixture_manifest.json`: roundtrip visible text **43,391 ตัวอักษรตรงกัน** หลัง collapse layout whitespace; คงสระ/วรรณยุกต์และลำดับข้อความ ไม่ทำ NFC/ตัดอักขระไทย
- `epubcheck-approved-44.json` และ `epubcheck-approved-cover.json`: EPUBCheck **5.3.0**, **0 fatal / 0 error / 0 warning** ตรวจ EPUB จริงทั้งไม่มีปกและปกจาก demo/01.png
- `approved_browser_network_log.json`: Chrome 154.0.8037.93 และ Edge 154.0.4258.53 ผ่าน Preview, source, คลิกสารบัญ, package, download, keyboard และ mobile; **external calls = 0**, page errors = 0
- `compatibility_matrix.json`: epub.js 0.3.93 และ Foliate commit ใน tool_versions.json เปิด EPUB จริงแบบ local ตรวจลิงก์สารบัญทุกจุด, ไทย, CSS, รูปปกและ resize/reflow ทั้งสอง browser
- `benchmark_budget.json`: ล็อกก่อนวัด preview/package p95 ไม่เกิน 5 วินาที, peak process RSS ไม่เกิน 256 MB; 10 รอบบนชุดจริง 44 หน้า
- `benchmark_results.json`: Preview p50/p90/p95 = 0.0803/0.0844/0.0846 วินาที; Package = 0.0586/0.0629/0.073 วินาที; peak RSS **59.29 MB**, 44 บท, 59,396 bytes ผ่านงบ
- Guard smoke check ใช้ approved_44pages_job: generation และ deletion ถูกปฏิเสธก่อนแก้ไฟล์/DB เมื่อ job busy ไม่ได้ลบข้อมูลจริง

## Regression และข้อจำกัดการปิดเกณฑ์

ก่อนพบกติกาชุดข้อมูล ได้รัน regression **17/17 PASS** และ browser flow สำหรับ invalid, stale/409, regenerate, Unicode, XSS, รูปปกเสีย, deterministic และ failed generation แต่มี fixture จำลอง จึง **แยกออกจากผลตรวจรับชุดอนุมัติ** และยังไม่ใช้ปิด checkbox edge cases

checklist.md บรรทัด 46 ห้าม fixture จำลอง ขณะที่ Phase 8 ต้องตรวจ RTL/zero-width/Unicode/XSS/ไฟล์เสีย ซึ่งไม่มีครบใน demo จึงรอคำตอบผู้ใช้เรื่องข้อยกเว้นสำหรับ regression เฉพาะความถูกต้อง/ความปลอดภัย Benchmark และตรวจรับเนื้อหาใช้ demo จริงต่อไป

ยังไม่อ้างการรับรอง desktop reader, JPEG คุณภาพจริง หรือชุดขยาย 2,229 หน้า ผล reader ที่บันทึกเป็น external browser engines 2 ตัว ทดสอบอัตโนมัติใน local harness

## รันทวน

```powershell
& .\publish\venv\Scripts\python.exe -m tests.phase8.benchmark
& .\publish\venv\Scripts\python.exe -m tests.phase8.approved_roundtrip
& .\publish\venv\Scripts\python.exe -m tests.phase8.approved_browser
java -jar .\tools\epubcheck\epubcheck-5.3.0\epubcheck.jar .\phase8\approved_reader_fixture.epub --json .\phase8\epubcheck-approved-cover.json
```

Regression ที่ใช้ fixture จำลองรอข้อยกเว้นก่อนรันทวนและปิดเกณฑ์:

```powershell
& .\publish\venv\Scripts\python.exe -m unittest discover -s tests\phase8 -p "test_*.py" -v
& .\publish\venv\Scripts\python.exe -m tests.phase8.browser_acceptance
```


## ขอบเขต Phase 8–9 ที่ใช้ร่วมกัน

Phase 8 ดูแลการสร้าง EPUB, XHTML Preview, สารบัญอัตโนมัติและรูปปก ส่วน Phase 9 ที่ยังเป็นแผนเพิ่มการแก้สารบัญด้วยมือ, toc.json และ stable targets โดยใช้ exporter/validator/ปกเดิม

ปกคง input สูงสุด 2 MB / 16 megapixels และ canonical PNG สูงสุด 8 MB ใช้ preview_payload.json.cover และ API preview/GET cover เดิม Phase 9 ไม่เพิ่ม storage ปกหรือ upload/delete API อีกชุด; thumbnail/drag-and-drop เป็นงาน UX เพิ่มเติม

Phase 9 จะเพิ่ม toc_revision ใน preview config เดิมที่รวม source/metadata/chapter split/cover hash งานเก่าไม่มี toc.json ใช้สารบัญอัตโนมัติได้ การทดสอบ EPUB/ปก/reader/CSP/offline ซ้ำเป็น regression และไม่ปิดข้อคงค้าง Phase 8 อัตโนมัติ ดู [ข้อตกลงร่วมและแผน](../checklist.md#ข้อตกลงร่วมระหว่าง-phase-8-และ-phase-9-2026-10-05)
