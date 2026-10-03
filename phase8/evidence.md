# Phase 8 Evidence — EPUB Export & XHTML Quick Preview

สถานะ: **กำลังพัฒนา / ยังไม่ผ่านการตรวจรับ**  
วันที่: 2026-10-03

## ผลที่ทำแล้ว

- เพิ่ม `src/epub_exporter.py` และสำเนาใน `publish/src/`
- สร้าง XHTML Quick Preview จาก `basic.html`, `ai.html` หรือ `final.html`
- ใช้ canonical block model ชุดเดียวกันสร้าง Preview และ chapter XHTML
- รองรับแบ่งบทตาม `h1` หรือหน้า
- สร้าง `mimetype`, `META-INF/container.xml`, `package.opf`, `nav.xhtml`, CSS และ chapter XHTML
- วาง `mimetype` เป็น ZIP entry แรกและไม่บีบอัด
- ตรวจ XML, manifest, spine, path และขนาด package ก่อนเผยแพร่ `book.epub`
- ตรวจ `base_preview_revision` และ source revision; ตอบ HTTP 409 เมื่อข้อมูลเปลี่ยนหลัง Preview
- เพิ่ม API สำหรับ Preview, package, status และ download
- เพิ่มหน้า Phase 8 ใน Web Studio พร้อม Metadata, XHTML Preview, Source view และปุ่มดาวน์โหลด
- Preview ใช้ sandbox และ CSP; ไม่มี CDN, external font หรือ EPUB renderer
- อัปเดต Source และชุด `publish/` ให้ตรงกัน

## ผลทดสอบปัจจุบัน

คำสั่ง:

```cmd
publish\venv\Scripts\python.exe -m unittest discover -s tests\phase8 -p "test_*.py" -v
```

ผล: **6/6 PASS**

ครอบคลุม:

- Quick Preview เป็น XHTML ที่ parse ได้
- ตัด `<script>` ออกจาก Preview และ EPUB
- Preview และ package รักษาข้อความภาษาไทยตัวอย่าง
- EPUB มี `mimetype` ถูกตำแหน่งและไม่บีบอัด
- internal package validator ผ่าน
- source เปลี่ยนหลัง Preview ถูกปฏิเสธ
- preview revision ผิดถูกปฏิเสธ
- สร้าง Preview ใหม่แล้ว EPUB package รุ่นก่อนถูกทำเครื่องหมาย stale และซ่อนจากการดาวน์โหลด
- API CSP sandbox, status, download, RFC 5987 และ nosniff

Smoke test ชุดอนุมัติ 44 หน้า:

- สร้าง Quick Preview สำเร็จ 44 บทเมื่อแบ่งตามหน้า
- สร้าง `book.epub` ขนาด 58,949 bytes
- internal validator: `valid=true`, errors 0
- status: `ready`, `stale=false`

## รายการที่ยังไม่ผ่านเกณฑ์ปิด Phase

- ยังไม่ได้ตรวจด้วย EPUBCheck เวอร์ชันที่ล็อก
- ยังไม่ได้ทดสอบเปิดใน EPUB reader ภายนอก 2 ตัว
- ยังไม่มี browser automation Chrome/Edge และ network log
- ยังไม่มี benchmark p50/p90/p95 และ peak memory
- ยังไม่มี fixture manifest/roundtrip ครบทุก Unicode edge case
- ยังไม่รองรับรูปปก
- สารบัญระดับย่อยและ accessibility audit ยังต้องตรวจเพิ่ม

ห้ามใช้เอกสารนี้อ้างว่า Phase 8 ผ่านสมบูรณ์จนกว่ารายการข้างต้นจะปิดครบ
