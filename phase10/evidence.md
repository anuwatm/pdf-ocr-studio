# Phase 10 Evidence — 2026-10-11

สถานะ: **IMPLEMENTATION COMPLETE / QUALITY ACCEPTANCE NOT COVERED**

## ผ่าน

- Translation schema 10.0, stable segment IDs, separate source/baseline/AI/final, deterministic revision และ stale/409 guards
- Local AI, Google Cloud Translation v3 ผ่าน ADC และ Hybrid ใช้ provider contract/error taxonomy เดียว
- Protected-token และ structure validator บล็อก publish เมื่อพบ critical-token change หรือตารางไม่มี cell model
- Background progress/cancel/retry/resume, Translation UI, glossary, 4-mode review, Text/HTML export และ translated EPUB Quick Preview
- Publish Phase 10: 23/23 PASS รวม core/provider/API/EPUB, `demo/08.pdf` structure และ browser Chrome/Edge 2/2
- Error matrix ผ่าน quota/auth/timeout/invalid JSON/cancel/retry/resume/restart/409/source-glossary stale
- Browser external request 0 และ page error 0 ใน local fixture
- Exploratory real-provider test `demo/12.png`: OneOCR completed 3,350 ตัวอักษร; Local AI `google/gemma-4-e2b`, `en` → `th`, style `novel` แปลครบ 41/41 และ export Text/HTML สำเร็จ หลังแก้ target-language validator, resume, protected-token handling และ prose/code detection
- Regression หลังแก้ real-provider issues: source 23/23 และ publish 23/23 PASS (รวม Chrome/Edge)
- Regression หลังเพิ่ม Text source และ Provider ราย adapter: publish 27/27 PASS (non-browser 25/25 + Chrome/Edge 2/2)
- Text source `final.txt`/`corrected.txt`/`raw.txt` ผ่าน stable segment, page split และ HTML escaping tests; Provider UI แสดง Local LLM API + AI CLI 5 ตัว + Google + Hybrid
- Translation source preview รองรับ HTML/Text ผ่าน CSP sandbox, target language default เป็นไทย และ AI CLI status ใช้ persisted cache ที่ตรวจจริงเฉพาะเมื่อผู้ใช้กดปุ่ม
- Chrome/Edge ยืนยัน source view, target `th`, image auto page count, page marker unchecked, cached CLI header และ manual CLI status check; publish regression 36/36 ผ่าน
- **Semantic Segment Assembly (Section 10.2A)**: เพิ่มชั้น `TranslationUnit` เชื่อม OCR lines เข้าเป็นประโยค/ย่อหน้าบริบทสมบูรณ์, ติดตาม BBox และ source spans ครบถ้วน, English de-hyphenation อัตโนมัติ (รองรับ soft hyphen `U+00AD`, รวมคำขาด `lay-` + `ers` → `layers` พร้อมกฎคงรูป compound word/URL/code/minus sign/capitalized boundary เคร่งครัด), บันทึก transformation log ระดับ unit, และ Reversible Export Mapping ที่คง HTML structure signature 100%
- **AI CLI Protocol & Sandboxing (Section 10.3A)**: กำหนด Canonical JSON Protocol Envelope (Schema 10.0), ส่ง payload ทาง `stdin`, บังคับ child process sandbox พร้อม environment allowlist `ALLOWED_CLI_ENV_VARS`, isolated scratch directory, output size ceiling 5MB, strict model/auth preflight checks, และ audit log เก็บครบ latency, input/output hash, validation result โดยไม่บันทึก credentials
- **Unit & Acceptance Regression (Section 10.6)**: ชุดทดสอบ `tests/phase10/` ทั้งหมด **47/47 PASS** (ประกอบด้วย core, providers, tasks, API/EPUB, approved structure `08.pdf`–`13.png`, semantic assembly, และ browser automation Playwright)

## ยังใช้ตัดสินคุณภาพคำแปลไม่ได้

- `demo/08.pdf`–`13.png` ล็อกเป็น input แล้ว แต่ยังไม่มีภาษาปลายทาง, ground truth, glossary และ style rubric ที่ผู้ใช้อนุมัติ
- ไม่มีชุดเอกสาร `ราชการ`
- เครื่องตรวจรับยังไม่มี `GOOGLE_CLOUD_PROJECT`/ADC จึงยังไม่มีผล Google/Hybrid จริง; Local LLM ทดสอบจริงแล้วหนึ่งชุด แต่ยังไม่ใช่ blind comparison
- ผล `demo/12.png` แบบ `novel` ยังไม่ผ่าน human quality review เพราะ OCR แบ่งบรรทัดจนคำ/ประโยคขาด และไม่ตรง style `academic` ที่ checklist กำหนด ดู `demo12_local_novel_th/evaluation.md`
- ยังไม่ทำ blind human review, EPUBCheck ภายนอก และ reader matrix กับคำแปลจริง

ดู `dataset_manifest.json`, `quality_report.json`, `prompt_manifest.json`, `glossary_manifest.json`, `benchmark_results.json` และ `browser_automation.json`
