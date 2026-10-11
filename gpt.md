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

### เริ่ม implementation — 2026-10-09

- เพิ่ม `translation.json` schema 10.0, stable segment/text-node mapping, deterministic revision, stale guard และ 409 conflict
- ตารางคง row/cell/rowspan/colspan; ตารางไม่มี `cell model` เป็น `unresolved` และบล็อก publish
- เพิ่ม style `ทั่วไป`/`นิยาย`/`วิชาการ`/`ราชการ`, prompt version 10.0.0 และกฎคงศัพท์เฉพาะ/ทับศัพท์
- เพิ่ม glossary revision, do-not-translate และสถานะ `translated`/`preserved`/`transliterated`
- เพิ่ม `TranslationProvider`: Local AI, Google Cloud Translation v3 ผ่าน ADC และ Hybrid; credential ไม่ส่ง browser/ไม่บันทึก artifact
- เพิ่ม protected-token validator สำหรับตัวเลข วันที่ เวลา เงิน เปอร์เซ็นต์ หน่วย URL อีเมล citation/code และศัพท์ glossary
- เพิ่ม background task, estimate/progress/cancel/retry/resume, transient backoff, audit, Text/HTML export และ source `translated` สำหรับ EPUB
- เพิ่มหน้า Translation: provider capability, cloud consent/cost estimate, glossary, 4-mode review, manual draft, accept/revert, retranslate strategy และเปิดต่อใน EPUB Studio
- Publish acceptance `tests/phase10/`: **23/23 PASS** รวม API, `demo/08.pdf` structural roundtrip, translated EPUB stale guard และ Chrome/Edge; external request/page error = 0 ใน local fixture
- Error matrix ครบ quota/auth/timeout/invalid JSON/cancel/retry/resume/restart/409/source-glossary stale; provider response ตรวจ ID/schema/language/size
- Regression: Phase 8 **17/17**, Phase 8.1 **12/12**, Phase 9 **9/9 PASS** หลังแก้ Translation capability ให้ lazy-load เฉพาะเมื่อเปิดแท็บ
- แก้ race ของ manual draft บน Edge โดยเก็บค่าทันทีต่อ segment เมื่อเกิด input; Chrome/Edge ผ่านซ้ำ
- ติดตั้ง `google-auth 2.61.0` ใน `publish/venv` และเพิ่ม `google-auth>=2,<3` ใน requirements; Google provider ยัง unavailable จนตั้ง `GOOGLE_CLOUD_PROJECT`/ADC
- เพิ่ม `phase10/evidence.md`, prompt/glossary/quality manifests, browser log และ benchmark 10 runs (p95 0.1391s, peak tracemalloc 20.05 MB; ไม่รวม provider latency)
- ซิงก์ source/publish และอัปเดต README/MANUAL/diagram/API/checklist แล้ว
- ผล Phase 10: **IMPLEMENTATION COMPLETE / QUALITY ACCEPTANCE NOT COVERED** เพราะยังไม่มี target language, ground truth, glossary/rubric, ชุดราชการ, provider จริง และ blind human review; ไม่อ้างคุณภาพคำแปล

## 2026-10-09 — ทดสอบจริง demo/12.png ด้วย Local AI แบบนิยาย → ไทย

- เปิด LM Studio local server และใช้ `google/gemma-4-e2b`; OneOCR สำเร็จ 1 หน้า, 3,350 ตัวอักษร, ตรวจ source เป็นอังกฤษ confidence 1.0
- ผลสุดท้ายของ pipeline: `completed`, 41/41 segments, warning 0 และสร้าง `translated.txt`/`translated.html` สำเร็จ
- ระหว่างทดสอบพบ false success: โมเดล copy อังกฤษบาง segments แต่ validator เดิมตรวจเฉพาะทั้งเอกสาร จึงเพิ่ม per-segment `target_language_mismatch` และให้สถานะ `partial`
- เพิ่ม resume โดย revalidate ผลเก่า, จำกัด Local/Hybrid batch ค่าเริ่มต้น 4 และรองรับ `LOCAL_TRANSLATION_BATCH_SEGMENTS=1..8`; ใช้ batch=1 กู้ segments ที่ Gemma แปลไม่ผ่าน
- Local AI ไม่แทน critical token ด้วย placeholder แล้ว เพราะโมเดลเล็กลบ placeholder; ให้เห็นตัวเลข/สูตรจริงและใช้ post-validator บล็อกเมื่อค่าหายหรือเปลี่ยน
- แก้ false positive: comma หลัง `Chapter 1,`, `i.e.` ที่ถูกนับเป็น code และ prose ที่มีคำว่า `function` ซึ่งเคยถูก preserve เป็น code
- Unit tests core/provider/tasks ผ่าน 18/18; Phase 10 regression source และ publish ผ่านฝั่งละ 23/23 (non-browser 21/21 + Chrome/Edge 2/2) หลังแก้
- Human review: **ยังไม่ผ่าน quality acceptance** แม้ pipeline ครบ เพราะ OCR แบ่งตามบรรทัดจนเกิด `hyperparameter / tuning`, `lay- / ers`, `ground / truth`; style `นิยาย` ไม่เหมาะกับหนังสือ IT และไม่ตรง checklist `12.png` ที่กำหนด `วิชาการ`
- หลักฐาน: `phase10/demo12_local_novel_th/evaluation.md`, `report.json` และ artifacts ใต้ `files/demo12/export/translation/`

## 2026-10-09 — เพิ่มผลแปลรวมทั้งหมดในหน้า Translation

- เพิ่มแผง `ผลแปลรวมทั้งหมด` รวม Final ทุก segment ตามลำดับเอกสาร คั่นย่อหน้าด้วยบรรทัดว่าง
- แสดงจำนวน segment/อักขระ และปุ่ม `คัดลอกทั้งหมด`
- ผลรวมไม่เปลี่ยนตามตัวกรองหน้า และอัปเดตทันทีเมื่อแก้ Final draft, ใช้ผลแปล หรือคืนต้นฉบับ
- เพิ่ม browser acceptance ตรวจผลรวมและ draft ข้ามหน้า; Chrome/Edge ผ่าน 2/2
- อัปเดต README, diagram, checklist และ sync source/publish

## 2026-10-09 — สำรวจ AI CLI สำหรับช่วยแปล

- พบ Gemini CLI, Codex CLI และ Aider; เตรียม prompt วิชาการจาก OCR `demo/12.png` ขนาด 4,633 bytes โดยยังไม่ส่งขึ้น cloud
- ทดลอง Codex CLI local provider แล้ว CLI เลือกดาวน์โหลด `openai/gpt-oss-20b` 12.11 GB แทน Gemma ที่มีอยู่ จึงหยุดที่ประมาณ 1.5%; ไม่มีผลแปลและไม่ลบ partial download เพราะต้องขออนุญาตก่อนลบ
- Gemini CLI local routing ยังไม่ setup และต้องดาวน์โหลด LiteRT-LM/model เพิ่ม
- Gemini CLI cloud เป็นตัวเลือกที่พร้อมที่สุด แต่ต้องมี consent ระบุ payload `demo/12.png` และปลายทาง Google Cloud ชัดเจน
- ข้อเสนอ: ใช้ AI CLI เป็น experimental provider/benchmark พร้อม stdin-only, no tools, JSON segment IDs, timeout/cancel, consent และ validator เดิม ไม่แทน API provider หลักทันที
- รายละเอียด: `phase10/ai_cli_trial/notes.md`

## 2026-10-09 — กำหนด Codex CLI และ Gemini CLI เป็น AI CLI หลัก

- ผู้ใช้กำหนดให้ `Codex CLI` และ `Gemini CLI` เป็น adapter หลัก; LM Studio CLI ลดเป็น adapter รองสำหรับ compatibility/local fallback
- ตรวจ CLI ที่ติดตั้ง: Codex CLI `0.150.1` รองรับ `codex exec` + stdin + JSONL/output schema; Gemini CLI `0.41.2` รองรับ stdin + headless + JSON/stream-json
- วิธีรับส่งหลัก: UTF-8 JSON/NDJSON ผ่าน stdin, structured JSON ผ่าน stdout และ diagnostic ผ่าน stderr
- Codex ต้องใช้ ephemeral/read-only/isolated workspace และ trusted output schema; Gemini ต้องใช้ headless/plan/sandbox และห้าม `--yolo`, `auto_edit`, `--raw-output`
- Codex/Gemini cloud ต้องมี consent พร้อมระบุ OpenAI/Google เป็นปลายทาง; local provider ต้อง preflight model และห้าม auto-download
- อัปเดต checklist Phase 10 แล้ว; implementation และ acceptance ของสอง adapter ยังเป็น `[ ]`

## 2026-10-09 — เพิ่มสถานะ AI CLI ในหน้า Local LLM Settings

- เพิ่ม `GET /api/ai/cli/status` ตรวจ Codex CLI, Gemini CLI และ LM Studio CLI แบบ read-only โดยไม่ส่งข้อความเอกสารออกเครื่อง
- แสดง installed/version, authentication, local runtime, adapter หลัก/รอง, เวลาตรวจล่าสุด และปุ่ม `ตรวจสอบอีกครั้ง`
- ใช้ fixed command + argument array + `shell=False`; UI render ด้วย `textContent`
- ผลตรวจจริง: Codex CLI `0.150.1` พร้อมและ login แล้ว; Gemini CLI `0.41.2` ติดตั้งแล้วแต่ Gemma local routing ยังไม่พร้อม; LM Studio CLI พร้อมเป็น adapter รอง
- Unit test ผ่าน 5/5; Chrome/Edge browser automation ผ่าน 2/2
- Phase 10 regression ผ่าน source 23/23 และ publish 23/23 หลังซิงก์ dependency ของ transport (`config.py`, `job_models.py`, `llm_client.py`)

## 2026-10-09 — เพิ่ม AI Command Interface: Codex / Gemini / AGY

- กำหนดตัวเลือก: ChatGPT CLI → `codex`; Gemini CLI → `gemini` หรือ `agy`; `lms` เป็น adapter รอง
- เพิ่ม `LLM_CLI_PROVIDER=codex|gemini|agy|lms` ใน config/API/.env และหน้า Settings แสดง selector เมื่อเลือก AI CLI
- Backend ใช้ allowlist executable และ `shell=False`; Codex/Gemini/AGY รับ prompt ผ่าน stdin ด้วย read-only/plan/sandbox mode
- เพิ่ม AGY ในแผง status; ตรวจเครื่องจริงได้ Codex `0.162.0`, Gemini `0.63.0`, AGY `1.3.2` และ LM Studio พร้อม โดย Gemma local routing ยังไม่พร้อม
- Unit tests 6/6 และ Chrome/Edge browser tests 2/2 ผ่าน; ยังไม่เรียก cloud generation เพราะต้องผ่าน consent ก่อน
- Phase 10 regression หลังเพิ่ม adapters ผ่าน source 23/23 และ publish 23/23

## 2026-10-09 — เพิ่ม Claude CLI

- เพิ่ม Claude CLI → `claude` ใน AI Command Interface และ `LLM_CLI_PROVIDER`
- อ้างอิง Claude Code CLI ทางการ: print mode `-p`, stdin, JSON output, `--permission-mode plan` และ `--max-turns`
- Adapter ใช้ isolated working directory, `--max-turns 1` และ block `Bash/Edit/Write/NotebookEdit/WebFetch/WebSearch`; ห้าม bypass permissions
- เพิ่มสถานะ Claude ในหน้า Settings; เครื่องนี้ยังไม่ติดตั้ง `claude` จึงแสดง `not_installed` และไม่มีการติดตั้ง/ส่ง cloud อัตโนมัติ
- Unit + Chrome/Edge tests ผ่าน 8/8 และ Phase 10 source regression ผ่าน 23/23
- Phase 10 publish regression ผ่าน 23/23 และ source/publish ซิงก์ตรงกัน

## 2026-10-09 — รับข้อเสนอ Gemini และปรับ Phase 10 checklist

- เห็นชอบให้ Semantic Segment Assembly + de-hyphenation เป็น Priority 1 ก่อนเปิด Translation Quality Gate
- เพิ่มข้อกำหนด reversible mapping จาก translation unit ไป original segment/char span/BBox, transformation log, stale/rebase และข้อห้าม merge ข้าม structure boundary
- บังคับ `12.png`/`13.png` ใช้ style `academic`; `13.png` ต้องผ่าน code preservation
- แก้ AI CLI checklist ให้แยก implementation/mock test/real provider acceptance และถอนข้อความที่เคลมว่า model preflight ครบทุก adapter
- ขยาย no-fallback, stdin, consent และ acceptance ให้ครอบคลุม Codex/Gemini/AGY/Claude/LM Studio
- แยก Quality Gate เป็น 3 providers หลัก × 4 translation styles; Phase 10 ยังคง `IMPLEMENTATION COMPLETE / QUALITY ACCEPTANCE NOT COVERED`

## 2026-10-09 — Translation รองรับ Text source และ Provider ราย adapter

- เพิ่มต้นทาง Text: `final.txt`, `corrected.txt`, `raw.txt`; `auto` ยังเลือก HTML ก่อน แล้ว fallback ไป Text
- Text ถูก escape และ wrap เป็น stable page/paragraph HTML ภายในก่อนเข้า segment pipeline เดิม จึงใช้ validator/revision/review/export ร่วมกันโดยไม่ OCR ใหม่
- หน้า Translation โหลด Provider จาก capability และเลือกได้: Local LLM API, Codex CLI, Gemini CLI, AGY CLI, Claude CLI, LM Studio CLI, Google และ Hybrid
- Backend route AI CLI ไป adapter ที่เลือกจริง; Codex/Gemini/AGY/Claude บังคับ cloud consent ส่วน Local LLM API/LM Studio CLI เป็น offline
- เพิ่ม `transport` และ `cli_adapter` ใน segment provenance/audit; รักษา `local` เดิมไว้เพื่อ backward compatibility ของงานเก่า
- Phase 10 publish regression ผ่าน 27/27: non-browser 25/25 และ browser automation Chrome/Edge 2/2; JavaScript syntax ผ่าน
- Capability endpoint คืน Provider ครบ 8 รายการภายในประมาณ 1 วินาทีในการตรวจครั้งนี้; ลด health check ซ้ำและยัง preflight adapter จริงก่อนเริ่มงาน

## 2026-10-10 — ปรับ Upload, Translation preview และ AI CLI status cache

- ปิด `ใส่เลขหน้าลงในไฟล์ข้อความ` เป็นค่าเริ่มต้นทั้ง UI และ API start request; งานเก่ายังอ่านค่าเดิมจาก artifact ได้
- เมื่อเลือก PDF/PNG/JPG/JPEG ระบบ upload และตรวจจำนวนหน้าอัตโนมัติทันที ก่อนผู้ใช้เลือกช่วงหน้าและเริ่ม OCR
- เพิ่ม `GET /api/jobs/{job_id}/translation/source/preview` และปุ่ม `View เอกสาร`; HTML/Text preview ใช้ CSP sandbox, Text escape ก่อนแสดง
- ภาษาปลายทาง Translation default เป็น `th` เมื่อ provider รองรับ และคงค่าที่ผู้ใช้เลือกเมื่อสลับ provider
- เปลี่ยน AI CLI status: `GET /api/ai/cli/status` อ่าน cache, `POST /api/ai/cli/status/check` ตรวจจริงเมื่อกดปุ่มและบันทึก `data/ai_cli_status.json`
- Header หน้าแรกแสดง AI CLI ที่ `ready` จาก cache โดยไม่สั่งตรวจซ้ำ
- Verification รอบสุดท้าย publish regression ผ่าน 36/36 รวม unit/API/static และ Chrome/Edge Settings + Translation/Upload/Header

## 2026-10-10 — แก้ UX Cloud privacy consent สำหรับ AI CLI

- แก้ข้อความ consent จาก Google แบบตายตัว เป็นปลายทางจริงตาม Provider: OpenAI/Codex, Google/Gemini/AGY/Cloud Translation, Anthropic/Claude หรือ Hybrid
- เปลี่ยน Provider แล้ว reset consent เพื่อไม่ใช้คำยินยอมของปลายทางเดิม
- ปุ่มเริ่มแปลตรวจ consent ใน browser ก่อนยิง API, focus checkbox และแจ้ง provider ที่ต้องยืนยัน
- Chrome/Edge browser acceptance สำหรับ Codex consent, provider switch reset และ Google consent ผ่าน 2/2

## 2026-10-10 — แก้ AGY CLI `--print` parsing

- เปลี่ยน AGY จาก `--print` ที่ไม่มีค่าเป็น `--print=<fixed instruction>` เพื่อไม่ให้ `--input-format` ถูกอ่านเป็น prompt
- เอกสารยังส่งทาง stdin; `--input-format text`, JSON output, plan/sandbox และ disable slash commands คงเดิม
- ข้อความ consent ใช้รูปแบบ `ยินยอมส่งข้อความ segment ไป Cloud AI ผ่าน <ชื่อ Provider>`
- Unit + Chrome/Edge acceptance ผ่าน 8/8; bump `translation.js` asset version เพื่อไม่ใช้ browser cache เดิม

## 2026-10-10 — แก้ผลแปล `09.png` จาก AGY CLI ไม่ถูกอ่าน

- ตรวจ job `job_d3f75e241f8c` ของ `09.png`: OCR สำเร็จ แต่ Translation ล้มเหลวที่ `Provider response missing segments` (`invalid_response`) จึงไม่มีผลแปล; ไม่ใช่ปัญหา OCR
- เพิ่มตัวแยก JSON envelope ของ CLI แบบ recursive รองรับ `result`/`message`/`content`/`parts` ซ้อนกัน, JSON ที่อยู่ใน string และ fenced JSON; จะคืนเฉพาะ payload ที่มี `segments` ให้ validator เดิมตรวจ ID/schema ต่อ
- รักษา stdin-only, `plan`, `sandbox` และ `shell=False`; ไม่บันทึก stdout หรือข้อความจากเอกสารลง log
- เพิ่ม regression test สำหรับ nested AGY/Gemini-style envelope; publish unit/API provider tests ผ่าน **13/13**
- การเรียก AGY จาก sandbox ของผู้พัฒนาเจอ credential-store access denied และไม่ authenticated จึงไม่ใช้ environment นี้สรุปผล provider จริง; ต้อง retry งานเดิมจาก runtime ที่ผู้ใช้ sign-in แล้วหลัง reload server

## 2026-10-10 — ตรวจรับงาน Gemini: AGY CLI และ Translation preflight

- อ่าน `gemini.md` และตรวจโค้ดจริง พบว่า patch AGY ของ Gemini ส่ง `combined` ซึ่งมีข้อความเอกสาร ผ่าน `--print=<prompt>` ใน command line แม้จะส่งซ้ำใน stdin ด้วย จึงขัด checklist 10.3A ที่ห้ามใส่ข้อความเอกสารใน command line, เสี่ยงข้อมูลอยู่ใน process list และชนเพดาน Windows
- แก้ AGY เป็น protocol ทางการ `--input-format stream-json --output-format stream-json`: ส่ง UTF-8 NDJSON `{event:user,message:{content:...}}` ทาง stdin อย่างเดียว แล้วอ่านเฉพาะ terminal `result.response` ที่ `status=SUCCESS`; stdout event อื่นและ stderr ไม่ถูกใช้เป็นผลแปล
- แก้ `_extract_cli_json_output()` ให้ตัด `<thought>`/`<thinking>`/`<analysis>` และ Markdown JSON fence ก่อน parse รวมถึงรองรับ JSON envelope ซ้อน; strict segment schema/ID validator ยังทำงานต่อเหมือนเดิม
- เพิ่ม preflight ที่ `TranslationTasks.start()`: ตรวจ capability ของ provider ก่อนสร้าง task/background thread; provider unavailable ถูก reject ทันที พร้อม test ครอบคลุมกรณี adapter ไม่ authenticated
- เพิ่ม tests: AGY ไม่มี document อยู่ใน argv, stdin เป็น NDJSON, nested envelope, reasoning/fence และ preflight unavailable; publish unit/API/provider/task ผ่าน **21/21**
- ไม่รับรองคำกล่าวใน `gemini.md` ว่า live AGY แปลสำเร็จ 100% เพราะตรวจซ้ำจาก sandbox ไม่ได้: AGY session นี้อ่าน credential store ไม่ได้และขอ OAuth. หลัง restart runtime ให้ retry `09.png` จาก session ที่ sign-in แล้ว; หาก AGY ส่ง response ผิด schema ระบบจะหยุดพร้อม error โดยไม่บันทึกผลเสีย

## 2026-10-11 — ตรวจรับ Gemini: Google Cloud Translation และ Local parser

- อ่าน `gemini.md` ฉบับ 2026-10-11 เทียบ `checklist.md`, source และ publish; ยืนยันว่า Google Cloud Translation config/API/UI มีอยู่จริง และ Phase 10 regression เดิมผ่าน 31/31
- พบ Local parser ของ Gemini มี fallback ที่ดึง JSON จากข้อความอิสระด้วย regex; ขัด checklist ที่กำหนดให้ reject ข้อความนอก JSON จึงตัด fallback นี้ออก และเพิ่ม regression `prefix {…}` ต้อง `invalid_response`
- พบ Google v3 ได้ HTTP 401/403 จะหยุดทันที แม้ตั้ง `GOOGLE_TRANSLATION_API_KEY` สำหรับ v2 ไว้แล้ว; แก้ให้ fallback ไป v2 เฉพาะกรณี v3 auth error และยังคงไม่ fallback สำหรับ quota/invalid request/server error
- เพิ่ม regression Google v3 403 → v2 success, แล้วรัน publish `tests/phase10`: **32/32 PASS** รวม Chrome/Edge
- ปรับ checklist AGY ให้ตรง implementation `stream-json` ผ่าน stdin; ยังไม่ check Quality Acceptance, Semantic Segment Assembly/de-hyphenation, strict auth/model preflight ทุก adapter, หรือ live provider matrix เพราะยังไม่มีหลักฐานจริงครบ

## 2026-10-11 — เริ่มแก้ Priority 1: Semantic Segment Assembly

- เพิ่ม `TranslationUnit` แบบ reversible ก่อนส่ง provider: รวมเฉพาะ OCR line-series ที่อยู่ page/block เดียวกัน, ไม่รวม table/code/list/heading และไม่แก้ source artifact หรือ original segment ID
- Unit เก็บ stable `id`, `member_ids`, source spans, page, member index และ transformation log; context `lay-` + `ers` จะเป็น `layers` เฉพาะ context สำหรับโมเดล ขณะที่ผลลัพธ์ยังต้องคืนตาม original segment ID ทุกตัว
- provider ได้ `context_unit` เพื่อแปล line เดิมโดยเห็นประโยคเต็ม; batch จะไม่แยกสมาชิกใน unit ข้ามกัน
- เพิ่ม `ASSEMBLER_VERSION=10.2.0`; translation เก่าที่ version ไม่ตรงถูกระบุ stale เพื่อไม่ทับ manual-final เงียบ ๆ
- เพิ่ม regression de-hyphenation, reversible member/span mapping และ unit-batch; publish core/task tests ผ่าน **18/18**
- ยังไม่ check ข้อ 10.2A ทั้งชุด: UI ระดับ unit, BBox highlight, export anchor/continuation suppression, soft-hyphen/compound guard และ ground truth ต้องทำต่อก่อน Quality Gate
- ทดสอบ AGY `09.png` ต่อไม่ได้ เพราะ artifact job `job_d3f75e241f8c` ไม่อยู่ใน `files/` หรือ `publish/files/`; พบเพียง `demo/09.png` ต้นฉบับ จึงไม่มี OCR/source artifact ที่ตรวจซ้ำโดยไม่สร้างงานใหม่

## 2026-10-10 — แก้ไข AGY CLI ไม่แปลภาษา (Missing segments / Invalid JSON)

- หาสาเหตุ: `agy` CLI ในโหมด print (`--print`) ไม่ได้อ่าน prompt จาก stdin; เมื่อส่งคำสั่งแบบ `--print=<fixed instruction>` โมเดลได้รับเพียงคำสั่งคงที่โดยไม่มีเนื้อหาเอกสารและ segments ส่งผลให้โมเดลพยายามเรียกเครื่องมือ (`RunCommand`) เพื่ออ่าน stdin ใน headless mode จนถูก headless permission guard บล็อก (`jetski: no output produced — a tool required the "command" permission...`) และคืนค่าว่าง `""` ทำให้ Translation ล้มเหลวที่ `Provider returned invalid JSON` หรือ `missing segments`
- แนวทางแก้ไขใน `src/llm_client.py`:
  1. ส่งเนื้อหา prompt และ segments รวมคำสั่งเข้าผ่าน `--print={agy_prompt}` โดยตรง
  2. กำหนดคำสั่งชัดเจนใน `agy_prompt` ว่าห้ามใช้เครื่องมือ/คำสั่งใดๆ ให้ตอบเฉพาะ JSON เท่านั้น
  3. ตั้งเพดานตรวจความยาว prompt 28,000 ตัวอักษรเพื่อไม่ให้เกินขีดจำกัด command-line ของ Windows
  4. ยังคงส่ง `input_text=combined`, `--sandbox`, `--mode plan` และ `--disable-slash-commands` เพื่อคงความปลอดภัยและรองรับ test suite
- ทดสอบจริงกับ `agy.exe`: `provider.translate()` แปลคำสำเร็จและคืน JSON โครงสร้างถูกต้อง (`Machine learning เป็นสาขาย่อยของปัญญาประดิษฐ์`, `computer vision`)
- ซิงก์โค้ด `src/llm_client.py` ไปยัง `publish/src/llm_client.py`; รันเทสต์ `tests.test_local_llm_config` ผ่าน 7/7 และ Phase 10 regression suite ผ่าน 27/27
