# Phase 9 — Editable TOC, stable targets และ cover UX

สถานะ: **PASSED / implementation และ automated acceptance ครบ**  
วันที่: 2026-10-06

## ผลส่งมอบ

- `toc.json` schema `9.0`: entry ID, label, parent ID, level 1–3, order, target ID, status, source revision และ TOC revision; atomic write
- stable heading target รักษา HTML `id` ที่ถูกต้อง; ID ที่ไม่มี/ซ้ำใช้ content hash และบันทึก `generated`/`duplicate-remapped`
- target เลือกได้จาก h1–h3 หรือต้นบท; href คำนวณจาก BookModel จึงไม่รับ path/URL จากผู้ใช้
- re-match ใช้ stable ID ก่อน และ unique match key เมื่อแน่นอน; target หาย/กำกวมเป็น unresolved และบล็อก Preview/package
- TOC editor แก้ชื่อ เพิ่ม เอาออก เลื่อน ปรับระดับ เลือก target และไปดูตำแหน่ง รองรับ keyboard/mobile
- draft คงอยู่เมื่อสลับมุมมอง/งาน; ยกเลิก re-match ไม่ทิ้ง draft; dirty state บล็อก Preview/package
- API GET/PUT/regenerate ตรวจ source/TOC/preview revision; สองแท็บหรือ config เปลี่ยนคืน 409
- Quick Preview และ `nav.xhtml` ใช้ TOC model เดียวกัน; source, TOC, metadata, chapter split หรือ cover เปลี่ยนทำให้ package stale
- cover UX มี thumbnail, drag-and-drop, MIME/dimensions/size และแยกปกที่เลือกค้างจาก Preview ที่บันทึก

## ผลทดสอบ

- Phase 9 source: `9/9 PASS`; publish standalone: `9/9 PASS`
- Phase 8 regression source/publish: `17/17 PASS`
- Phase 8.1 regression: `12/12 PASS`
- Chrome/Edge: edit/reorder/nesting/add/remove/save/reload/cancel draft/Preview/package/drag-drop cover/mobile/keyboard ผ่าน
- external request `0`; browser page error `0`; Local AI ไม่ถูกเรียก
- approved 44-page roundtrip: 43,391 visible characters ตรง source และ hash demo 6 ไฟล์ตรง baseline
- deterministic package: byte-identical เมื่อใช้ source/config/TOC revision เดิม

## EPUB และ readers

- `approved_phase9.epub`: 44 content chapters + cover, TOC 27 entries, internal validator ผ่าน
- EPUBCheck 5.3.0: `0 fatal / 0 error / 0 warning / 0 usage`
- epub.js และ Foliate บน Chrome/Edge: label ที่แก้, ทุก TOC target, cover และ reflow resize ผ่าน
- reader external calls `0`; page errors `0`

## Performance

- งบล็อกก่อนวัด: Preview p95 ≤ 5s, package p95 ≤ 5s, RSS ≤ 256MB, 10 runs
- ผล: Preview p50 `0.2098s`, p95 `0.3230s`; package p50 `0.1239s`, p95 `0.2945s`; RSS `62.83MB`
- ผลรวม: `PASS`

## หลักฐาน

- `package_report.json`, `epubcheck.json`, `reader_matrix.json`
- `benchmark_budget.json`, `benchmark_results.json`
- `approved_phase9.epub`
- `tests/phase9/`

## ขอบเขต

- ไม่เพิ่ม `toc.ncx`; EPUB 3.3 ใช้ `nav.xhtml`
- target จากย่อหน้าใดก็ได้และการย้าย/แบ่งเนื้อหาผ่าน TOC editor อยู่นอกขอบเขตรุ่นแรก
- ผลนี้ไม่เปลี่ยน manual ground-truth gate ที่ยังคงอยู่ใน Phase 8.1
