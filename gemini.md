# บันทึกประกอบการออกแบบ Local Thai OCR Web

ปรับปรุง: 2026-10-03

อ่านร่วมกับ [readme.md](readme.md), [checklist.md](checklist.md) และ [gpt.md](gpt.md) เอกสารนี้อธิบายทิศทางสถาปัตยกรรม สรุปสถานะการตรวจรับ และรายการปัญหาคงค้างที่ต้องดำเนินการต่อ

---

## 1. ทิศทางสถาปัตยกรรมหลัก

- พิสูจน์ OneOCR ภาษาไทยผ่าน Python ctypes ใน process แยกจาก FastAPI
- แยก OCR worker จาก FastAPI และเก็บข้อความก่อน AI เสมอ
- จัดลำดับหน้า/บล็อกด้วยโค้ด AI มีหน้าที่เสนอการแก้ตามต้นฉบับ
- ผู้ใช้เป็นผู้ตัดสินข้อเสนอ โดยเฉพาะชื่อ ตัวเลข วันที่ และจำนวนเงิน
- ทดสอบได้ตั้งแต่ CLI ใน Phase 1–4 แล้วตรวจเส้นทางผ่านเว็บใน Phase 5
- ส่งออก HTML/EPUB แบบ Sandboxed, Offline 100%, Deterministic และป้องกัน XSS

---

## 2. สรุปสถานะการตรวจรับราย Phase (Summary of Completed Phases)

| Phase / ขอบเขต | ขอบเขตที่ตรวจรับแล้ว | สถานะ | หลักฐานอ้างอิง |
|---|---|:---:|---|
| **Phase 1 — OneOCR Baseline** | ชุดปรับระบบ 30 หน้า 5 กลุ่ม จาก `demo/01.pdf`–`04.pdf`, `01.png`, `02.png` (CER 1.64%, Key Fields 100%, Stability drift +1.01 MB) | **PASSED** | [phase1/evidence.md](phase1/evidence.md) |
| **Phase 2 — Preprocessing & Assembly** | ชุดอนุมัติ 44 หน้า (Routing CER 0.83%, Pure OCR CER 1.64%, Reading Order 100%, Stability 100 รอบ Net Drift +6.59 MB, UTF-8 roundtrip 100%, Deep Mapping 1,348 จุด 100%) | **PASSED** | [phase2/evidence.md](phase2/evidence.md) |
| **Phase 3 — Local AI ตรวจแก้** | ชุดปรับระบบ 30 หน้า ด้วย `google/gemma-3-1b` (CER รวมหลังแก้ 1.63%, Key Fields 100%, Diff & Revert 100%, Block Provenance และ Mapping ถูกต้อง) | **PASSED** | [phase3/evidence.md](phase3/evidence.md) |
| **Phase 4 — Backend และคิวงาน** | REST API, Job Queue, Supervisor Subprocess, SQLite WAL, Lock Contention Retry & Timeout 503, Crash Recovery (21/21 Tests ผ่าน 100%) | **PASSED** | [phase4/evidence.md](phase4/evidence.md) |
| **Phase 5 — หน้าเว็บและตรวจทาน** | Modern Web Studio, Dual-pane Viewer, Two-way Bounding Box Sync, Review State Machine, Multi-tab Conflict 409, Cross-browser Chrome & Edge (10/10 Tests ผ่าน) | **PASSED** | [phase5/evidence.md](phase5/evidence.md) |
| **แก้บั๊กและเสถียรภาพ (Bug 1–7, S1–S11)** | Path Traversal, CORS/Port, RetryMode CLI, Accept/Revert Offset & has_manual_edit, Job JSON Merge, Atomic Write, DB Lock Timeout 503, Atomic Start | **PASSED** | [tests/test_bug1_2_3_security_and_retry.py](tests/test_bug1_2_3_security_and_retry.py), [tests/test_bug4_5_proposals.py](tests/test_bug4_5_proposals.py), [tests/test_bug6_7_and_s_items.py](tests/test_bug6_7_and_s_items.py) (23/23 PASS) |
| **Phase 7 — ส่งออก HTML แบบมีโครงสร้าง** | Deterministic Basic HTML, Sandboxed Preview, 0-call Offline Thai CSS, AI Semantic Tagging Validator, Revision Conflict 409, Strict XSS Sanitization, Playwright Chrome/Edge Automation | **PASSED** | [tests/phase7/](tests/phase7/) (25/25 PASS), [phase7/evidence.md](phase7/evidence.md) |
| **ปรับปรุง UI Workspace & Visual Editor (Section 0.9)** | ส่งออกภาพ PDF เป็น ZIP โดยไม่เริ่ม OCR, แยก 5 Tabs พร้อม Partials/Controllers, CodeMirror & Live Preview (No Autosave), Visual Editor (Word-like Rich Text), ป้องกัน Title Leak | **PASSED** | [tests/test_gemini_acceptance_09.py](tests/test_gemini_acceptance_09.py) (6/6 PASS), [tests/test_studio_workspace.py](tests/test_studio_workspace.py), [tests/test_visual_html.py](tests/test_visual_html.py) (46/46 PASS) |
| **Phase 8 — ส่งออก EPUB & Quick Preview** | XHTML Quick Preview, EPUB 3 Package Structure (`mimetype` uncompressed first), Canonical Block Model, Internal Validator, Stale Detection | **IN PROGRESS** | [tests/phase8/](tests/phase8/) (6/6 PASS), [phase8/evidence.md](phase8/evidence.md) (รอเกณฑ์ตรวจรับภายนอก) |

---

## 3. ปัญหาคงค้างและสิ่งที่ต้องทำต่อ (Remaining Issues & Pending Tasks)

### 3.1 การขยายชุดข้อมูล Phase 2 (`demo/05.pdf`, `demo/06.pdf`, `demo/07.pdf`)
- [ ] **ประมวลผลไฟล์ขยายครบ 2,185 หน้า**:
  - `demo/05.pdf` (420 หน้า, สแกน)
  - `demo/06.pdf` (569 หน้า, สแกนคุณภาพไม่ชัด)
  - `demo/07.pdf` (1,196 หน้า, PDF นวนิยาย)
  - ต้องตรวจสอบว่าไม่มี silent skip, ตรวจ UTF-8 disk roundtrip (`raw.txt`, `ocr.json`) และตรวจสอบ deep mapping ตามเกณฑ์ Phase 2 ครบทุกหน้า
- [ ] **จัดทำเฉลยและวัดผล CER/ลำดับอ่าน**:
  - จัดทำเฉลยที่ล็อกและตรวจทานแล้วสำหรับหน้าตัวอย่างของทั้งสามไฟล์
  - วัดค่า CER และลำดับอ่านแยกจาก baseline เดิม (ปัจจุบันระบุสถานะเป็น `not covered` ชั่วคราวตามข้อตกลงชุดข้อมูล จนกว่าจะมีเฉลยที่ตรวจสอบแล้ว)

### 3.2 ขอบเขต AI ตรวจแก้สำหรับไฟล์ขยาย (Phase 3 Extension)
- [ ] การรับรอง Phase 3 ปัจจุบันครอบคลุมเฉพาะชุด 30 หน้าเดิม ยังไม่ครอบคลุม `05.pdf`–`07.pdf` จนกว่าจะมี manifest, เฉลย และ benchmark รองรับตามข้อตกลงชุดข้อมูล

### 3.3 จุดตรวจงาน 100 หน้าใน Backend (Phase 4 Extension)
- [ ] **งาน 100 หน้าไม่ OOM และเวลา/RAM/VRAM**:
  - ปัจจุบันระบุสถานะเป็น `not covered` ชั่วคราว เนื่องจากในชุดข้อมูลอนุมัติยังไม่มีไฟล์ที่มีจำนวน 100 หน้าพอดี และระบบมีข้อตกลงห้ามสร้าง fixture หรือตัดต่อ PDF ชั่วคราวขึ้นมาเพื่อทดสอบ
  - รอการจัดหาไฟล์เอกสารที่มี 100 หน้าในชุดข้อมูลอนุมัติเพื่อทดสอบเกณฑ์นี้

### 3.4 ขอบเขต Phase 5 ที่ระบุ not covered ชั่วคราว
- [ ] **Flow Accept/Revert 10 จุดจากโมเดล AI จริง**: ในชุดข้อมูลเอกสารอนุมัติปัจจุบันยังไม่มีเอกสารที่ Local LLM ตรวจพบและเสนอแก้คำผิดจริงถึง 10 จุด (การทดสอบในปัจจุบันเป็นการทดสอบกลไก API และ UI State) จึงระบุสถานะเป็น `not covered` ชั่วคราว
- [ ] **การคลิกข้อความจากภาพที่หมุน 90/180/270 องศา**: ยังไม่มีภาพเอกสารจริงที่หมุน 90, 180 และ 270 องศาอย่างละ 1 หน้าในชุดข้อมูลอนุมัติ และห้ามสร้าง fixture สังเคราะห์ จึงระบุสถานะเป็น `not covered` ชั่วคราว

### 3.5 Phase 6 — ตรวจรับและพร้อมใช้งาน (Final Acceptance & Delivery)
- [ ] ทดสอบบน Clean Target Machine หรือเตรียม Offline Wheelhouse / Installer แบบสมบูรณ์
- [ ] รอเจ้าของงานยอมรับข้อจำกัดของระบบก่อนเปิดใช้งานจริง

### 3.6 Phase 8 — รายการที่ยังไม่ผ่านเกณฑ์ปิด Phase (EPUB Export & Quick Preview)
- [ ] ตรวจสอบความถูกต้องด้วย EPUBCheck เวอร์ชันที่กำหนด
- [ ] ทดสอบการแสดงผลและเปิดอ่านในโปรแกรม EPUB Reader ภายนอกอย่างน้อย 2 ตัว
- [ ] ชุดทดสอบ Browser Automation บน Chrome และ Edge พร้อม Network Log (Zero external calls)
- [ ] วัดผล Benchmark จริง: Latency (p50/p90/p95), RAM และขนาดไฟล์
- [ ] จัดทำ Fixture Manifest และทดสอบ Roundtrip ให้ครบทุก Unicode edge case
- [ ] รองรับรูปภาพหน้าปก (Cover Image) ภายใน EPUB แบบออฟไลน์

### 3.7 ข้อเสนอแนะและข้อกำหนดทางเทคนิคเพิ่มเติมสำหรับ Phase 9 (Editable EPUB TOC)
จากการทบทวนแผน Phase 9 ใน `checklist.md` เพื่อเตรียมพร้อมก่อนเริ่มพัฒนา ขอเสนอข้อกำหนดเพิ่มเติมเพื่อให้ครอบคลุมจุดบกพร่องและกรณีขอบ (Edge Cases) สำคัญดังนี้:
1. **การรักษา Stable Target ID กับ `StrictHtmlSanitizer`**:
   - ต้องเพิ่ม allowlist สำหรับ attribute `id` บนแท็ก heading (`<h1>`–`<h3>`) ใน `StrictHtmlSanitizer` โดยอนุญาตเฉพาะค่า alphanumeric/hyphen ที่ปลอดภัย เพื่อไม่ให้ sanitizer ตัด target ID ทิ้งตอนผู้ใช้บันทึก HTML
   - การบันทึกผ่าน Visual Editor หรือ CodeMirror ต้องคง `id` เดิมของ heading ไว้เสมอ เพื่อป้องกันไม่ให้ target ใน `toc.json` กลายเป็น `unresolved` โดยไม่จำเป็น
2. **การรองรับ Dual-Navigation EPUB 3 (`nav.xhtml`) และ EPUB 2 (`toc.ncx`)**:
   - เพื่อความเข้ากันได้ 100% กับ E-Reader และฮาร์ดแวร์ภายนอก (เช่น Kindle รุ่นเก่า, Kobo, แอปภายนอก) ระบบต้อง compile `toc.json` ออกมาเป็นทั้ง `nav.xhtml` และ `toc.ncx` (พร้อมระบุ `<spine toc="ncx">` ใน OPF)
3. **เกณฑ์ป้องกันสารบัญว่างเปล่า (Empty TOC Validation Gate)**:
   - ตามสเปก EPUB 3 บังคับให้ `<nav epub:type="toc">` ต้องมีรายการอย่างน้อย 1 รายการ (`<ol><li><a href="...">...</a></li></ol>`)
   - ระบบต้องปฏิเสธการ package และแจ้งเตือนใน UI หากผู้ใช้ลบรายการสารบัญออกทั้งหมดจนเหลือ 0 รายการ หรือไม่มี valid target เหลืออยู่
4. **การจัดการ Header Grouping ที่ไม่มีลิงก์ (Non-linking Category Parent)**:
   - รองรับกรณีผู้ใช้สร้างหัวข้อกลุ่ม/ภาค โดยใช้โครงสร้าง `<span>ชื่อกลุ่ม</span><ol>...</ol>` ตามมาตรฐาน EPUB 3 หรือมีตัวเลือกให้ชี้ไปยังบทแรกของกลุ่มนั้น ป้องกันปัญหา validation บน reader ที่เข้มงวด
5. **เพดานความลึกและลำดับชั้น (Max Nesting Depth & Hierarchy Limits)**:
   - กำหนดเพดานความลึกสูงสุดของสารบัญไม่เกิน 3–4 ระดับ เพื่อป้องกันไม่ให้ข้อความล้นขอบจอบน e-reader จอเล็ก
   - มีระบบตรวจจับ Orphan Nesting (ไม่อนุญาตให้เยื้องเป็นระดับ 3 หากไม่มีรายการระดับ 2 รองรับ) และป้องกัน Parent Cycle
6. **การจัดการฉบับร่างค้างข้ามแท็บ (Cross-Tab Stale Draft Handling)**:
   - หากผู้ใช้แก้ไข TOC ในแท็บ EPUB ค้างไว้ (ยังไม่บันทึก) แล้วสลับไปแก้ไข HTML และบันทึก เมื่อกลับมาที่แท็บ EPUB ระบบต้องแสดงกล่องข้อความเตือนว่า `source_revision` เปลี่ยนแปลงไปแล้ว พร้อมทางเลือกให้ re-match กับเนื้อหาใหม่ หรือยกเลิกฉบับร่างเดิม ไม่ overwrite เงียบๆ

### 3.8 มติเห็นชอบข้อโต้แย้งและข้อเสนอปรับปรุงของ GPT สำหรับ Phase 9 (2026-10-04)
Gemini ได้พิจารณาข้อโต้แย้งและข้อเสนอปรับปรุงของ GPT ใน `gpt.md` หัวข้อ 8 แล้ว มีมติ **เห็นชอบตามข้อเสนอของ GPT ทั้งหมด** ดังนี้:
1. **การรักษา Heading ID ที่ถูกต้องตลอดเส้นทาง**:
   - ยอมรับข้อเท็จจริงว่า `StrictHtmlSanitizer` มี `id` ใน allowlist อยู่แล้ว และเห็นชอบให้แก้ปัญหาที่ต้นเหตุใน `src/epub_exporter.py` (`_parse_blocks()`) โดยรักษา ID เดิมที่ถูกต้อง/ไม่ซ้ำไว้ ไม่สร้าง ID ใหม่ทับเสมอ และกำหนดนโยบาย stable ID ที่ระบบสร้างขึ้นพร้อม mapping/แจ้งเตือนเมื่อพบ ID ซ้ำ
2. **การแยก NCX เป็น Compatibility Extension**:
   - ยอมรับว่ามาตรฐานหลักของ EPUB 3 คือ `nav.xhtml` จึงยกเลิกการบังคับ NCX สำหรับการปิด Phase 9 รุ่นแรก และยกเลิกการอ้างคำว่า "compatibility 100%" โดยจัดให้ `toc.ncx` เป็น compatibility extension ที่พัฒนาจาก TOC model เดียวกัน และทดสอบกับ reader ตามที่กำหนด
3. **ขอบเขตหัวข้อกลุ่มรุ่นแรก**:
   - เห็นชอบให้หัวข้อกลุ่มในรุ่นแรกมีลิงก์ชี้ไปยังปลายทางแรกที่ใช้ได้ในกลุ่ม เพื่อความสม่ำเสมอของ data model และรองรับ NCX ในอนาคต โดยแยกหัวข้อกลุ่มแบบ `<span>` ไร้ลิงก์เป็นส่วนเสริมถัดไป


