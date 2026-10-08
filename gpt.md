# ปัญหาคงค้าง

อัปเดต: 2026-10-05

เก็บเฉพาะงานค้างและหลักฐานที่ยังไม่ครบ ตัดประวัติการแก้ไขและงานที่ตรวจรับแล้วออก ดูสรุปผลตรวจรับใน [gemini.md](gemini.md)

ไฟล์ `gemini.md` เป็นความเห็นของ Gemini จึงอ่านอย่างเดียวเสมอ

## 1. ชุดข้อมูลขยายยังไม่ผ่าน Phase 2

ขอบเขตที่ยังไม่รับรอง: `demo/05.pdf` (420 หน้า, สแกน), `demo/06.pdf` (569 หน้า, สแกนไม่ชัด) และ `demo/07.pdf` (1,196 หน้า, native text layer และหน้าว่างจริง)

- [ ] ประมวลผลครบ 2,185 หน้า โดยไม่มี silent skip
- [ ] ตรวจ UTF-8 roundtrip, block/line mapping และ routing ของผลบนดิสก์ครบทุกหน้า
- [ ] จัดทำ ground truth ที่ล็อกและตรวจซ้ำ แล้ววัด CER, key fields และลำดับอ่านของหน้าตัวอย่างที่กำหนด

จนกว่าจะผ่าน ขอบเขต Phase 2 ที่รับรองแล้วมีเฉพาะ `demo/01.pdf`–`04.pdf` และ `demo/01.png`–`02.png` รวม 44 หน้า

## 2. ชุดข้อมูลขยายยังไม่ผ่าน Phase 3

Phase 3 รับรองแล้วเฉพาะ baseline เดิม 30 หน้า/ขอบเขตเอกสาร 44 หน้า

- [ ] หลัง Phase 2 ของไฟล์ `05.pdf`–`07.pdf` ผ่านแล้ว ให้สร้าง benchmark AI จาก manifest และ ground truth ที่ล็อกสำหรับไฟล์ขยาย
- [ ] รายงาน CER ก่อน/หลัง AI, key fields, diff/revert, mapping และ stale revision แยกจาก baseline เดิม

## 3. งบงาน 100 หน้าใน Phase 4

- [ ] `not covered` ชั่วคราว: ยังไม่มีเอกสารอนุมัติที่มี 100 หน้าและผ่านเพดานรับเข้า 100 หน้า

ห้ามใช้ `tests/phase4/test_100_pages_budget.py` เป็นหลักฐาน เพราะสร้าง PDF 100 หน้าชั่วคราวจาก `demo/07.pdf` ซึ่งขัดข้อตกลงชุดข้อมูลทดสอบ

## 4. หลักฐานรับรอง Phase 5 ยังไม่ครบ

- [ ] `not covered` ชั่วคราว: ยังไม่มีเอกสารจริงที่ให้ Local LLM สร้างข้อเสนอแก้ไขได้ 10 จุด จึงยังรับรอง flow accept/revert 10 จุดจากข้อมูลจริงไม่ได้
- [ ] `not covered` ชั่วคราว: ยังไม่มีภาพเอกสารจริงที่หมุน 90/180/270 องศาอย่างละ 1 หน้า จึงยังรับรองการตรวจและหมุนแก้ใน UI ไม่ได้

## 5. Phase 6 ที่ยังค้าง

- [ ] ชุดขยาย 2,185 หน้า: ไม่ควรยกเว้นเป็น `not covered` เพราะมีเอกสารจริงอยู่แล้วและเป็นส่วนหนึ่งของชุดข้อมูลอนุมัติ ต้องประมวลผลครบ, ตรวจ mapping/disk output และจัดทำ ground truth ก่อนอ้างผลครอบคลุมทั้งชุด
- [ ] Clean installation: สภาพ offline เป็นข้อจำกัดชั่วคราวได้ แต่ไม่พอสำหรับรับรองการส่งมอบสุดท้าย ต้องทดสอบบน clean target machine หรือจัดเตรียม wheelhouse/installer แบบ offline
- [ ] รอเจ้าของงานยอมรับข้อจำกัดก่อนเปิดใช้งานจริง

## 6. หลักฐานวัดผล Phase 7 ที่ยังไม่ครบ

Gemini รับรอง implementation ของ Phase 7 แล้ว แต่ [phase7/evidence.md](phase7/evidence.md) ยังระบุผลวัดต่อไปนี้เป็น `not covered`:

- [ ] วัด AI HTML latency และ VRAM จาก Local LLM จริง พร้อมบันทึกวิธีวัดและผลที่ตรวจซ้ำได้
- [ ] จัดทำ element-level ground truth ที่ผู้ตรวจรับรอง แล้วคำนวณ precision/recall/F1 ของ heading, paragraph และ bold จากเฉลยจริง
- [ ] เมื่อมีหลักฐานครบ ปรับสถานะในเอกสารและ benchmark ให้ตรงกัน ไม่ใช้ค่าคงที่หรือค่าประมาณเป็นผลวัดจริง

## 7. Phase 8 — สถานะปัจจุบันและเกณฑ์คงค้าง

พัฒนา EPUB, XHTML Preview, สารบัญอัตโนมัติและปกแล้ว หลักฐานชุดอนุมัติ 44 หน้าใน [phase8/evidence.md](phase8/evidence.md) ครอบคลุม EPUBCheck 5.3.0 ไม่มี error/warning, reader engines ภายนอก 2 ตัวแบบ local, Chrome/Edge, zero external calls, benchmark และ roundtrip ของชุดจริง

- [ ] เกณฑ์ completed/partial/cancelled และ markers, Unicode edge cases, payload อันตราย, invalid/stale/409/regenerate ตาม checkbox ที่ยังค้างใน checklist.md ต้องปิดด้วยหลักฐานที่กติกาชุดข้อมูลอนุญาต
- [ ] ข้อยกเว้น fixture จำลองสำหรับ regression ความถูกต้อง/ความปลอดภัยยังรอผู้ใช้ ไม่ถือว่าคำขอปรับขอบเขต Phase 8–9 อนุมัติข้อยกเว้นนี้
- บันทึก Gemini หัวข้อ 3.6 เป็นความเห็นก่อนผลล่าสุด จึงอ้าง evidence/checklist สำหรับสถานะปัจจุบัน โดยไม่แก้ความเห็นหรืออ้างการตรวจรับใหม่แทน Gemini
- ความสามารถปกอยู่ Phase 8; Phase 9 ใช้ต่อและเพิ่ม UX เท่านั้น ไม่ย้ายเกณฑ์คงค้าง Phase 8 ไปปิดใน Phase 9

## 8. Phase 9 — มติเดิมและการใช้ระบบ Phase 8 ร่วมกัน (2026-10-04)

มติข้อโต้แย้งเดิมได้รับความเห็นชอบใน gemini.md หัวข้อ 3.8 แล้ว; Phase 9 implementation และ automated acceptance เสร็จ 2026-10-06

### ข้อที่เห็นด้วยและเพิ่มใน checklist แล้ว

- รักษา stable heading ID ตลอด CodeMirror/Visual/sanitizer/EPUB และตรวจ ID ซ้ำ
- ห้าม package สารบัญว่างหรือไม่มี valid target พร้อมตรวจชื่อว่าง
- ล็อกเพดานรุ่นแรกที่ 3 ระดับให้ตรงกับ h1–h3 และตรวจ orphan/parent cycle; เป็นข้อกำหนดของแอป
- เก็บ TOC draft เมื่อ HTML เปลี่ยน พร้อม re-match/ยืนยันทิ้งฉบับร่างและแสดง unresolved ก่อนบันทึก

### ข้อที่ควรปรับจากข้อเสนอ Gemini

1. **ข้อเท็จจริงเรื่อง allowlist ของ ID**
   - `StrictHtmlSanitizer.ALLOWED_ATTRS` ใน `src/html_exporter.py` และ `allowedAttrs` ใน `static/visual.js` มี `id` อยู่แล้ว จึงไม่ใช่งานเพิ่ม allowlist ใหม่ทั้งหมด
   - จุดที่พบใน `src/epub_exporter.py` คือ `_parse_blocks()` สร้าง `heading-{heading_index:04d}` ใหม่ตามลำดับ
   - ขอแก้ acceptance เป็นรักษา ID ที่ถูกต้อง/ไม่ซ้ำครบทั้งเส้นทาง และกำหนดนโยบาย ID ที่ระบบสร้าง ส่วน ID เดิมที่ผิดนโยบายต้องมี mapping/แจ้งเตือน ไม่ลบทิ้งเงียบ ๆ
   - [x] Gemini ยอมรับการแก้คำอธิบายและเกณฑ์นี้ (ดู `gemini.md` หัวข้อ 3.8)

2. **ไม่เห็นด้วยกับการบังคับ NCX เพื่ออ้าง compatibility 100%**
   - EPUB 3 ใช้ navigation document; NCX เป็นส่วนรองรับระบบเก่า การเพิ่ม NCX อย่างเดียวไม่ได้เปลี่ยนไฟล์ให้เป็น EPUB 2 หรือรับประกันอุปกรณ์ทุกตัว
   - เสนอให้ `toc.ncx` เป็น compatibility extension แยกจากเกณฑ์ปิด Phase 9 รุ่นแรก ไม่ตัดการทดสอบ EPUBCheck/reader เดิม
   - หากต้องเพิ่ม NCX ให้สร้างจาก TOC model เดียวกัน ระบุ manifest/spine ให้ถูกต้อง และทดสอบ reader/version ที่ระบุจริง รวมการ mapping หัวข้อกลุ่ม
   - อ้างอิง: [EPUB 3.3 — NCX](https://www.w3.org/TR/epub-33/#sec-opf2-ncx)
   - [x] Gemini ยอมรับการแยก NCX เป็นส่วนเสริมและยกเลิกคำอ้าง compatibility 100% (ดู `gemini.md` หัวข้อ 3.8)

3. **หัวข้อกลุ่มไม่มีลิงก์: เห็นด้วยว่ามาตรฐานรองรับ แต่เสนอจำกัดรุ่นแรก**
   - EPUB nav รองรับ span เป็นชื่อกลุ่ม โดยต้องมี ol ลูก; span เป็น leaf ไม่ได้
   - เสนอรุ่นแรกให้หัวข้อกลุ่มชี้ปลายทางแรกที่ใช้ได้ในกลุ่ม พร้อมแสดงเป้าหมายให้ผู้ใช้ยืนยัน หากไม่มีเป้าหมายต้อง unresolved ไม่เดาเลือกนอกกลุ่ม
   - เหตุผล: ใช้กติกา target เดียวกับรายการทั่วไป ลดความต่างของ Preview/nav และ NCX หากเพิ่มภายหลัง; ไม่ได้อ้างว่ามาตรฐานห้ามกลุ่มไม่มีลิงก์
   - กลุ่มแบบ span ไม่มีลิงก์ให้แยกเป็นส่วนเสริม พร้อมกำหนดพฤติกรรมเมื่อเอารายการลูกสุดท้ายออก
   - อ้างอิง: [EPUB 3.3 — Navigation restrictions](https://www.w3.org/TR/epub-33/#sec-nav-elem)
   - [x] Gemini ยอมรับขอบเขตหัวข้อกลุ่มรุ่นแรก (ดู `gemini.md` หัวข้อ 3.8)

สถานะข้อโต้แย้ง: **Gemini พิจารณาเห็นชอบแล้ว (2026-10-04)** บันทึกมติใน `gemini.md` หัวข้อ 3.8 และล็อกขอบเขต Phase 9 ใน `checklist.md` เรียบร้อยแล้ว


### การแบ่งงานและสัญญาข้อมูลร่วมกับ Phase 8

- Phase 8 เป็นเจ้าของ EPUB pipeline, BookModel, ปก, Preview/download และ validator; Phase 9 เพิ่ม TOC editor, toc.json และ stable targets
- ใช้ปกเดิมใน `preview_payload.json.cover` และ hash/config เดิม; เพิ่มหน้าปก 2 แหล่ง: upload PNG/JPEG สูงสุด 10 MB หรือ render PDF ต้นฉบับ 1 หน้าตามเลขที่เลือก โดยไม่ OCR ซ้ำ บันทึก `source_type/source_page`, จำกัด 16 megapixels และ canonical PNG 20 MB

## 2026-10-08 — EPUB cover 2 แบบ

- เพิ่ม UI เลือก `อัปโหลดรูปเอง` หรือ `ใช้หน้า PDF` พร้อม Thumbnail และตรวจช่วงเลขหน้าจาก PDF ต้นฉบับ
- เพิ่ม API `GET /api/jobs/{job_id}/export/epub/cover/pdf-pages` และ `GET /api/jobs/{job_id}/export/epub/cover/pdf-page/{page_num}`; เลขหน้าเกินช่วงคืน 422 และไม่ clamp ไปหน้าอื่น
- อัปโหลดรองรับ PNG/JPEG ไม่เกิน 10 MB; exporter sanitize, re-encode และฝังเป็น canonical PNG สูงสุด 20 MB
- ทดสอบไฟล์ JPEG 4,345,347 bytes ซึ่งเกินเพดานเดิม 2 MB ผ่าน, render `demo/08.pdf` หน้า 1 ผ่าน และปฏิเสธหน้าเกินช่วงผ่าน

## 2026-10-08 — Upload document สูงสุด 300 MB

- เปลี่ยนเพดาน `MAX_FILE_SIZE_BYTES` และ validation หน้า Upload จาก 50 MB เป็น 300 MB
- Backend ยังคงอ่านไฟล์เป็น chunk 64 KB และรองรับ `max_size_limit` สำหรับลดเพดานรายคำขอ; ไฟล์เกินเพดานคืน HTTP 413
- อัปเดต badge, error message, README, Manual และ checklist พร้อม cache version ของ `app.js`

## 2026-10-09 — แก้ UX ตัวอย่างหน้าปก EPUB จาก PDF

- Thumbnail เปิดดูภาพขนาดใหญ่ใน modal ได้ด้วย click หรือปุ่ม `ดูภาพขนาดใหญ่`; ปิดด้วยปุ่ม, backdrop หรือ Escape และใช้งานคีย์บอร์ดผ่านปุ่มได้
- เปลี่ยนปุ่มเป็น `แสดงตัวอย่างและเลือกเป็นปก`; หลัง render แสดง `เลือกเป็นหน้าปกแล้ว` และบอกให้สร้าง XHTML Quick Preview เพื่อบันทึก
- หลัง Preview สำเร็จแสดง `บันทึกใน XHTML Preview แล้ว` เพื่อลดความสับสนระหว่าง draft selection กับ persisted cover
- Phase 9 เพิ่ม toc_revision ใน preview config เดิม และตรวจ base TOC/source/preview revision เพื่อไม่ทับปก/metadata ที่อีกแท็บแก้
- thumbnail/drag-and-drop/รายละเอียดปกเป็น UX ที่เพิ่มบนของเดิม; ตรวจ EPUBCheck/reader/offline/ปกซ้ำเป็น regression
- ถ้าต้องเปลี่ยน transport/storage หรือเพดานปก ให้แยกข้อเสนอและ migration ออกจาก Phase 9 รุ่นแรก
- มติ NCX เป็นส่วนเสริม, กลุ่มชี้ target แรก และเพดาน UI 3 ระดับคงเดิม; รายละเอียดปัจจุบันอยู่ checklist.md ข้อตกลงร่วมและ Phase 9

## Phase 8.1 — งานเสริมตามคำขอผู้ใช้ (2026-10-05)

- [x] พัฒนา structured OCR ตาราง/รายการ, Text/HTML, หน้าเทียบต้นฉบับ และส่งต่อ EPUB ตาม checklist.md Phase 8.1
- มีเพียง prototype demo/04.pdf: จัด 36 เซลล์ด้วย PDF vector table + bbox OneOCR; พบ pipeline เดิมรวมข้อความแถว 04/05 ยังไม่ใช่ผลตรวจรับฟีเจอร์
- คง Phase 9 สำหรับ TOC editor/stable targets และไม่ถือว่าคำขอนี้อนุมัติ fixture จำลอง

ชุดทดสอบ Phase 8.1 เพิ่มเติม: `demo/08.pdf` ภาษาอังกฤษและตาราง 11 หน้า ผู้ใช้อนุมัติ 2026-10-05 ครอบคลุมตัวอย่างเซลล์รวม/หัวตารางหลายระดับ/คอลัมน์จาก tab stops; ยังไม่ผ่าน OCR acceptance ดู [แผนทดสอบ](checklist.md#phase8-1) และ [manifest](phase8_1/dataset_manifest.json) ไม่เปลี่ยนผลตรวจรับชุดเดิม

### เริ่ม implementation — 2026-10-06

- [x] เพิ่ม `src/structured_layout.py`: layout schema 1.0.0, fallback งานเก่า, vector table, tab-stop fallback, list model และ deterministic Text/HTML
- [x] Pipeline บันทึก layout พร้อมผล OCR งานใหม่; API `/export/structured` ใช้ artifact เดิมโดยไม่ OCR/AI ซ้ำ
- [x] เพิ่มหน้า Structured OCR เทียบต้นฉบับ/HTML เลือกหน้า ซูม เลือก cell/block และ keyboard/mobile mode
- [x] 2026-10-08 เพิ่มปุ่ม `OCR เป็น Text` / `OCR เป็น HTML` ในหน้า Upload; ปุ่ม HTML ใช้ OCR งานเดียวและสร้าง Structured HTML จาก artifact เดิมโดยไม่ OCR ซ้ำ
- [x] 2026-10-08 เพิ่ม `เปิดใน HTML Studio` จาก Structured OCR รองรับ Code/Visual และรักษา table/block/cell/bbox attributes เมื่อบันทึก `final.html`
- [x] `demo/04.pdf` ได้ 9×4/36 cells; `demo/08.pdf` 11 หน้า พบ 29 tables และหน้า 5 ได้ colspan=2
- [x] เพิ่ม scanned-table pixel detector, OCR-to-vector cell mapping, heading/list evidence และ raw/corrected/final แยก revision
- [x] AI HTML รักษา table/list; EPUB source `structured` รักษาตารางและ stale guard บล็อก package เก่า
- [x] Source/publish suite ฝั่งละ 12/12 PASS; Chrome/Edge ผ่าน raw/corrected/final, download, stale, mobile, keyboard; external request 0; console error 0
- [x] EPUBCheck 5.3.0 = 0 fatal/error/warning; epub.js และ Foliate บน Chrome/Edge ผ่าน reflow
- [x] Benchmark 10 runs ผ่านงบ p95 ≤ 5s / RSS ≤ 256MB: p95 0.6804s, RSS 61.15MB
- [x] ซิงก์ source/publish และอัปเดต README/checklist/คู่มือ/หลักฐานแล้ว
- [ ] จุดตรวจรับสุดท้าย: เจ้าของงานยืนยัน ground truth ทุก cell ใน demo/04 และค่าที่รองรับใน demo/08; private-use checkbox glyph 9 จุดคง unresolved ตามจริง
- หลักฐาน: `phase8_1/evidence.md`

### ผลตรวจรับรอบปิด implementation — 2026-10-06

- ผล: **ผ่านด้าน implementation และ automated acceptance**
- ผ่าน: vector/scanned table, OCR cell mapping, Text/HTML, AI preservation, stale revision, UI, EPUB, EPUBCheck, reader reflow, offline และ benchmark
- ชุดอนุมัติ: `demo/04.pdf` vector+scan derivative ตรง fixture 36/36 cells; `demo/08.pdf` 11 หน้า/29 tables
- คงค้างเฉพาะ manual gate: human ground truth; ระบบรายงาน private-use glyph 9 จุดเป็น unresolved และไม่เดาค่า
- ห้ามเปลี่ยนสถานะ Phase 8.1 เป็นผ่านสมบูรณ์จนเจ้าของงานยืนยัน manual gate

## Phase 9 — ผล implementation และตรวจรับ (2026-10-06)

- [x] เพิ่ม `src/toc_editor.py` และ `toc.json` schema 9.0: stable target, nested TOC 3 ระดับ, atomic save และ revision conflict
- [x] รักษา HTML heading ID; ID ไม่มี/ซ้ำใช้ deterministic hash และ `duplicate-remapped`
- [x] เพิ่ม API GET/PUT/regenerate TOC พร้อม base source/TOC/preview revision และ HTTP 409
- [x] Quick Preview และ `nav.xhtml` ใช้ TOC model เดียว; unresolved/stale บล็อก package
- [x] UI แก้ชื่อ/ลำดับ/ระดับ/target เพิ่ม/เอาออก ดูตำแหน่ง save/reload/re-match และคง draft
- [x] ปกมี thumbnail, drag-and-drop, MIME/dimensions/size และ dirty Preview state
- [x] Source/publish Phase 9 `9/9 PASS`; Phase 8 regression `17/17 PASS`; Phase 8.1 `12/12 PASS`
- [x] Approved 44-page roundtrip 43,391 chars ตรง; deterministic package ผ่าน
- [x] EPUBCheck 5.3.0 = 0 fatal/error/warning; epub.js/Foliate Chrome/Edge ผ่านทุก target/cover/reflow; external calls 0
- [x] Benchmark 10 runs ผ่าน: Preview p95 0.3230s, package p95 0.2945s, RSS 62.83MB
- ผล: **PASSED ด้าน implementation และ automated acceptance**; พร้อมให้ Gemini ตรวจรับอิสระ
- หลักฐาน: `phase9/evidence.md`, `phase9/package_report.json`, `phase9/epubcheck.json`, `phase9/reader_matrix.json`

## Phase 10 — แผนระบบแปลเอกสาร (2026-10-06)

- สถานะ: **PLANNED / ยังไม่เริ่ม implementation**
- เลือกภาษาต้นทาง/ปลายทางและ style: `ทั่วไป`, `นิยาย`, `วิชาการ`, `ราชการ`
- provider ที่วางแผน: Google Cloud Translation v3, Local AI และ Hybrid (Google baseline → AI polish)
- ใช้ stable segment/cell/target ID เดิม รักษาตาราง รายการ heading และ TOC; source/Google/AI/manual-final แยก artifact
- เพิ่ม glossary/do-not-translate, revision/stale/409, background progress/cancel/retry และ validator ชื่อ–ตัวเลข–วันที่–เงิน–หน่วย–citation
- กฎร่วมทุก style: ไม่บังคับแปลทุกคำ; ศัพท์เฉพาะทาง ชื่อเทคโนโลยี ชื่อผลิตภัณฑ์ ตัวย่อ และคำที่แปลแล้วคลาดเคลื่อน ให้คงคำเดิมหรือใช้คำทับศัพท์ตาม glossary/context พร้อมสถานะ `translated`/`preserved`/`transliterated`
- Google/Hybrid เป็น opt-in เพราะส่งข้อความออกจากเครื่อง; credential อยู่ backend ผ่าน ADC/service account เท่านั้น
- ส่งออก translated Text/HTML/EPUB ผ่าน pipeline เดิม และต้องสร้าง XHTML Quick Preview ก่อน package
- quality gate ต้องใช้ชุดข้อมูลคู่ภาษาที่ผู้ใช้อนุมัติ ประเมิน blind human review เทียบ Google/Local/Hybrid; metric อัตโนมัติเป็นหลักฐานเสริม
- ก่อนเริ่มต้องล็อก: คู่ภาษา, ชุดนิยาย/วิชาการ/ราชการ/ทั่วไป, glossary, provider/model/version และงบ latency/RAM/ค่าใช้จ่าย
- ผู้ใช้อนุมัติ input Phase 10 วันที่ 2026-10-06: `demo/08.pdf` ตารางอังกฤษ, `09.png` จีน+อังกฤษ/ศัพท์เฉพาะ, `10.png`–`11.png` นิยายอังกฤษ, `12.png` หนังสือสอน IT และ `13.png` หนังสือสอน IT ที่มี code program; hash/ขอบเขตอยู่ใน `phase10/dataset_manifest.json`
- ชุดนี้ยังรอ ground truth/ภาษาปลายทาง และยังไม่ครอบคลุม style `ราชการ`; ห้ามอ้างผล quality acceptance จนกว่าจะปิดเงื่อนไขดังกล่าว
- รายละเอียด: `checklist.md` Phase 10
