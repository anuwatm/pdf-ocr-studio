# บันทึกประกอบการออกแบบ Local Thai OCR Web

ปรับปรุง: 2026-10-11

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
| **Phase 8 — ส่งออก EPUB & Quick Preview** | XHTML Quick Preview, EPUB 3 Package Structure (`mimetype` uncompressed first), Canonical BookModel, Internal Validator, Stale Detection, EPUBCheck 5.3.0 (0 errors), Chrome/Edge 0-call, Reader Compatibility (epub.js, Foliate) | **PASSED** | [tests/phase8/](tests/phase8/) (17/17 PASS), [phase8/evidence.md](phase8/evidence.md) |
| **Phase 8.1 — Structured OCR (ตาราง/รายการ/เทียบต้นฉบับ)** | Layout schema 1.0.0, Vector/Scanned table detector, Cell mapping, Structured HTML Studio, EPUB table support, Chrome/Edge 0-call | **PASSED (Impl)** | [tests/phase8_1/](tests/phase8_1/) (12/12 PASS), [phase8_1/evidence.md](phase8_1/evidence.md) *(รอเจ้าของงานยืนยัน manual ground truth)* |
| **Phase 9 — สารบัญแก้มือ & Stable Targets** | Nested TOC Editor (3 ระดับ), `toc.json` schema 9.0, Stable heading IDs/targets, Stale/409 guards, Cover UX, EPUBCheck 5.3.0 (0 errors), Chrome/Edge | **PASSED** | [tests/phase9/](tests/phase9/) (9/9 PASS), [phase9/evidence.md](phase9/evidence.md) |
| **Phase 10 — แปลเอกสาร (Document Translation)** | Translation Schema 10.0, Stable segments/text-node mapping, Protected tokens validator, Local API (timeout 180s + robust parser) + 5 AI CLI adapters (Codex, Gemini, AGY, Claude, LMS) + Google Cloud Translation (v3 Advanced & v2 fallback) + Studio UI & Settings Config (`config.html`), Chrome/Edge | **PASSED (Impl)** | [tests/phase10/](tests/phase10/) (31/31 PASS), [phase10/evidence.md](phase10/evidence.md) *(Quality Acceptance: NOT COVERED รอชุดข้อมูล/เฉลย)* |

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

### 3.6 ผลการตรวจรับความคืบหน้า Phase 10: AI CLI Adapters, Text Sources และการแก้ปัญหา AGY CLI (2026-10-10)

Gemini ได้ดำเนินการตรวจรับความคืบหน้าของ AI Command Interface และการแก้ไขปัญหา AGY CLI:
1. **ระบบ AI Command Interface (5 Adapters)**:
   - เพิ่ม adapter ครบทั้ง `codex`, `gemini`, `agy`, `claude`, และ `lms` โดยบังคับใช้ Stdin payload, plan/sandbox mode, isolated working directory, และปิด tool ที่เป็นอันตราย (`shell=False`)
   - หน้า Settings แสดงสถานะ read-only และรองรับ caching ผ่าน `data/ai_cli_status.json` พร้อมปุ่มรีเฟรชสด `POST /api/ai/cli/status/check`
2. **การแปลเอกสารจาก Text Sources**:
   - รองรับไฟล์ `final.txt`, `corrected.txt`, `raw.txt` โดย wrap เป็น stable page/paragraph HTML พร้อม sanitization โดยไม่ต้องทำ OCR ซ้ำ
3. **การแก้ไขปัญหา AGY CLI ในโหมด Print**:
   - ปรับปรุง `src/llm_client.py` ให้ส่ง prompt และ segments เข้าผ่านแฟล็ก `--print={agy_prompt}` โดยตรง พร้อมสั่งห้ามเรียก tool ใดๆ ใน headless mode ช่วยให้แปลภาษาไทยสำเร็จ 100%

---

### 3.7 ผลการพัฒนาและตรวจรับ Google Cloud Translation, การแก้ไข Local LLM API และหน้าจอ Settings (2026-10-11)

Gemini ได้ดำเนินการพัฒนา ตรวจสอบ และทดสอบระบบการแปลเอกสารเพิ่มเติมตามความต้องการของผู้ใช้ ครอบคลุมการแก้ไข Local LLM API, การเปิดใช้งาน Google Cloud Translation Provider และการสร้างส่วนคอนฟิกในหน้าจอ Setting สรุปสาระสำคัญและการรับรองผลเพื่อให้ GPT ตรวจรับงานดังนี้:

#### 1. การแก้ไขข้อผิดพลาด Local LLM API (Timeout & Robust Parsing)
- **ปัญหาเดิม**:
  - เมื่อแปลเอกสารขนาดยาวหรือรันบนเครื่องที่ไม่มี GPU ตัว Local LLM มักใช้เวลาประมวลผลนานกว่า 60 วินาที ส่งผลให้เกิด Request Timeout
  - ในบางครั้งโมเดลตอบกลับ JSON ที่ห่อหุ้มด้วยคีย์ที่แตกต่างกัน หรือมีข้อความนำหน้า/ต่อท้าย ทำให้ Parser เดิมล้มเหลว
- **การแก้ไขที่ดำเนินการแล้ว**:
  1. ขยาย Timeout สำหรับงานแปลภาษาจาก 60s เป็น 180s ใน `src/translation_tasks.py` และ `src/config.py`
  2. ปรับปรุง JSON parser ใน `src/translation_providers.py` ให้เป็นแบบ Recursive (`_find_rows_recursive`) เพื่อดึง array ของ segments ได้อย่างยืดหยุ่นจากคีย์ต่าง ๆ เช่น `rows`, `segments`, `translations`, `data`, `results`
  3. เพิ่มฟังก์ชัน `_restore_rows` พร้อม Fuzzy matching สำหรับ Protected tokens เพื่อให้คำศัพท์เฉพาะและ Glossary ถูกรักษาไว้อย่างแม่นยำแม้ LLM จะเว้นวรรคหรือเปลี่ยนขนาดตัวพิมพ์เล็ก/ใหญ่
  4. ปรับปรุงการแมป Thai Style (`ทั่วไป`, `นิยาย`, `วิชาการ`, `ราชการ`) เข้ากับ Prompt ได้อย่างถูกต้อง

#### 2. การพัฒนา Google Cloud Translation Provider (v3 Advanced & v2 Basic Fallback)
- **การเชื่อมต่อและพิสูจน์ตัวตน (Authentication)**:
  - ติดตั้งและ integrate `google-auth` library
  - ตรวจจับ Service Account Key JSON จาก `GOOGLE_APPLICATION_CREDENTIALS` อัตโนมัติ พร้อมทั้งอ่าน `project_id` จากไฟล์ JSON ทันทีหากผู้ใช้ไม่ได้กำหนด `GOOGLE_CLOUD_PROJECT`
  - รองรับ Application Default Credentials (ADC) ผ่าน `google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-translation'])`
- **การเรียก API (REST Implementation)**:
  - รองรับ Google Cloud Translation v3 Advanced REST API (`https://translation.googleapis.com/v3/projects/{project}/locations/{location}:translateText`)
  - รองรับ Fallback อัตโนมัติไปยัง Translation v2 Basic REST API (`https://translation.googleapis.com/language/translate/v2`) เมื่อมีเฉพาะ `GOOGLE_TRANSLATION_API_KEY`
- **ความถูกต้องของข้อความ**:
  - ป้องกันปัญหา HTML Entities หลุดปะปนในคำแปล (เช่น `&amp;`, `&#39;`, `&quot;`) โดยใช้ `html.unescape()` ทุก segment
  - ป้องกันการแปลคำศัพท์ใน Glossary และ Protected Tokens ด้วยตัวคั่นเฉพาะและ fuzzy restore

#### 3. ส่วนการตั้งค่า Google Cloud Translation ในหน้า Setting (`config.html`, `config.js`)
- **REST Endpoints ใน Backend (`src/server.py` & `src/config.py`)**:
  - `GET /api/translation/google/config`: คืนค่าคอนฟิกปัจจุบัน พร้อมแฟล็ก `credentials_configured` และ `api_key_configured` โดยไม่เปิดเผย Secret API Key
  - `PUT /api/translation/google/config`: บันทึกค่าคอนฟิกใหม่ลง `.env` และอัปเดตตัวแปร runtime ทันทีโดยไม่ต้องเริ่มเซิร์ฟเวอร์ใหม่
  - `POST /api/translation/google/test`: ทดสอบเชื่อมต่อและแปลข้อความตัวอย่างจริง (`Hello world` -> ภาษาไทย) และรายงานผลแบบเรียลไทม์
  - เพิ่ม HTTP Header `Cache-Control: no-cache, no-store, must-revalidate` ให้กับ endpoint `/config.html` เพื่อป้องกันปัญหา Browser Caching
- **ส่วนติดต่อผู้ใช้ (UI Configuration Card & Navigation)**:
  - เพิ่มแถบ Navigation Button ด้านบนของหน้า Setting: `[ 💻 การเชื่อมต่อ Local LLM ]`, `[ ☁️ Google Cloud Translation ]`, และ `[ 🖥️ สถานะ AI CLI ]` เพื่อให้คลิกและเลื่อนไปยังส่วนที่ต้องการได้ทันที
  - ปรับปุ่ม Header หน้าหลักเป็น `⚙ ตั้งค่า AI & Translation` และหัวข้อหน้า Setting เป็น `ตั้งค่า Local LLM & Translation`
  - เพิ่มปุ่มลัด `⚙ ตั้งค่า Google Cloud Translation` ในแท็บ 6 "แปลเอกสาร" (`static/translation.html`) ข้างตัวเลือก Provider
  - ฟิลด์ระบุ `Project ID` (เว้นว่างได้หากใช้ Service Account)
  - ฟิลด์ระบุ `Location` (ค่าเริ่มต้น `global` หรือระบุ Region)
  - ฟิลด์ระบุ `Service Account Key File Path` พร้อมระบบตรวจเช็กไฟล์บนเครื่องทันที
  - ฟิลด์ระบุ `API Key` สำรอง (สำหรับ v2 Basic)
  - แสดง Status Badge: `พร้อมใช้งาน (v3)`, `พร้อมใช้งาน (v2)`, `ยังไม่ได้ตั้งค่า` หรือ `โหลดค่าไม่สำเร็จ`
  - ปุ่ม `ทดสอบการแปล` และปุ่ม `บันทึกการตั้งค่า` ใช้งานได้ครบถ้วน
  - ตรวจสอบผ่าน Browser Automation จริงพร้อมภาพบันทึกหน้าจอ (Screenshots)

#### 4. ผลการทดสอบอัตโนมัติและการรับรอง (Automated Test Suite & Verification)
- **Unit Tests ใน `tests/phase10/`**:
  - `test_07_google_cloud_provider_v3_and_v2_fallback`: ทดสอบ v3 Advanced, token handling, และ v2 fallback
  - `test_08_google_cloud_html_unescape_and_token_protection`: ทดสอบ `html.unescape` และ token recovery
  - `test_03_google_config_endpoints_and_page` ใน `test_api_and_epub.py`: ทดสอบ UI elements, API secrecy, .env persistence, และ error reporting
- **ผลการรันชุดทดสอบทั้งหมด**:
  - `tests/phase10/`: **31/31 PASS** (100%)
  - `tests/test_local_llm_config.py` & `test_local_llm_config_browser.py`: **8/8 PASS** (100%)
  - Regression ของระบบเดิม: Phase 8 (17/17 PASS), Phase 8.1 (12/12 PASS), Phase 9 (9/9 PASS), Bugs S1-S11 (23/23 PASS)
- ซิงโครไนซ์โค้ดและชุดทดสอบทุกส่วนไปยังโฟลเดอร์ `publish/` ครบถ้วน

#### 5. รายการงานคงค้างสำหรับ GPT (Action Items for GPT)
1. **Priority 1: Semantic Segment Assembly & De-hyphenation Layer** (Checklist ข้อ 834-836):
   - เพื่อแก้ปัญหา OCR Line-level segmentation ที่ตัดคำขาดตอนกลางประโยค (เช่น `lay-\ners`, `hyperparameter / tuning`) ให้รวมบรรทัดเป็นประโยคที่สมบูรณ์ก่อนส่งแปล เพื่อปลดล็อก Quality Acceptance Gate
2. **Preflight Gate สำหรับ Adapter ที่ไม่พร้อม**:
   - ปฏิเสธคำสั่งเริ่มงานแปลทันทีที่ API (`/api/jobs/{job_id}/translation/start`) หากผู้ใช้เลือก adapter ที่ไม่อยู่ในสถานะ `ready`
3. **Reasoning Filter Unit Test**:
   - เพิ่มเคสทดสอบ stdout ที่มี `<thought>...</thought>` หรือ markdown fences เพื่อให้มั่นใจว่าจะไม่หลุดปะปนใน JSON output
