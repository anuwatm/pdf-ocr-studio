# คู่มือการติดตั้ง เริ่ม/หยุดระบบ ตรวจสอบข้อผิดพลาด และข้อจำกัด (System Operations Manual)

**โครงการ:** Local Thai OCR Web  
**อัปเดต:** 2026-10-04 — OCR, HTML AI background tasks และ EPUB Studio  
**สถาปัตยกรรม:** Localhost Single-User Web Application (Loopback 127.0.0.1)

---

## 1. บทนำและสถาปัตยกรรมระบบ

ระบบแปลง PDF/ภาพเป็นข้อความภาษาไทย (Local Thai OCR Web) ได้รับการออกแบบสำหรับการใช้งานบน Windows 10/11 64-bit ภายในเครื่องเดี่ยว (Localhost Desktop) ทำงานแบบ 100% Offline ไม่ส่งเอกสารออกภายนอก

### ส่วนประกอบหลัก:
1. **Frontend:** Web Studio พัฒนาด้วย HTML5, Modern CSS และ Vanilla JavaScript รองรับ Dual-Pane Viewer, Bidirectional Bounding Box Sync, Diff Review และ Multi-tab Conflict Prevention
2. **Backend API:** Python FastAPI รันบน Uvicorn ผูกเข้ากับ Loopback `127.0.0.1:8000` โดยปฏิเสธการเชื่อมต่อจาก IP ภายนอก (HTTP 403 Forbidden)
3. **OCR Worker:** Python Subprocess แยกอิสระจาก FastAPI เพื่อความปลอดภัย โดยโหลด OneOCR DLL (`oneocr.dll`, `oneocr.onemodel`, `onnxruntime.dll`) ภายใน Worker เท่านั้น ป้องกัน native crash ไม่ให้กระทบตัวเว็บเซิร์ฟเวอร์
4. **Database & Storage:** SQLite โหมด Write-Ahead Logging (WAL) พร้อม timeout 5000ms และระบบจัดเก็บไฟล์แยกตาม Job ID (`files/{job_id}`)

---

## 2. การติดตั้งในสภาพแวดล้อมสะอาด (Clean Installation Guide)

### ความต้องการของระบบ (Prerequisites)
- **ระบบปฏิบัติการ:** Windows 10 หรือ Windows 11 (64-bit AMD64)
- **Python:** Python 3.10 หรือใหม่กว่า (แบบ 64-bit เท่านั้น ห้ามใช้ 32-bit เพราะ DLL เป็น 64-bit)
- **หน่วยความจำ (RAM):** ขั้นต่ำ 4 GB (แนะนำ 8 GB ขึ้นไป)
- **พื้นที่ดิสก์:** ขั้นต่ำ 1 GB สำหรับ dependencies และโมเดล

### ขั้นตอนการติดตั้งทีละขั้นตอน:

1. **เตรียมโฟลเดอร์โปรเจกต์และตรวจสอบไฟล์ OneOCR:**
   ตรวจสอบว่าในไดเรกทอรี `oneOCR/` มีไฟล์ครบทั้ง 3 ไฟล์:
   ```text
   oneOCR/
   ├── oneocr.dll
   ├── oneocr.onemodel
   └── onnxruntime.dll
   ```

2. **สร้างและเปิดใช้งาน Virtual Environment:**
   ```powershell
   py -3 -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

3. **ติดตั้ง Dependencies:**
   ```powershell
   py -3 -m pip install --upgrade pip
   py -3 -m pip install fastapi uvicorn pypdfium2 pymupdf pillow python-dotenv openai python-multipart
   ```

4. **ตั้งค่า Environment File (`.env`):**
   สร้างหรือแก้ไขไฟล์ `.env` ที่ root ของโปรเจกต์:
   ```env
   # Local Server Binding (Default: Loopback only)
   HOST=127.0.0.1
   PORT=8000
   LOCALHOST_ONLY=true

   # Local LLM Integration (Optional - for AI text correction)
   LLM_BASE_URL=http://127.0.0.1:1234/v1
   LLM_MODEL=google/gemma-3-1b
   LLM_TIMEOUT=60.0

   # Data Retention TTL in seconds (Default: 86400s = 24 hours)
   RETENTION_SECONDS=86400.0
   ```

### ตั้งค่า Local LLM ผ่านหน้าเว็บ

หลังเริ่มระบบ เปิด `http://127.0.0.1:8000/config.html` แล้วกำหนด `Base URL`, `Model`, `API key` (ถ้ามี) และ `Timeout` จากนั้นกด **ทดสอบการเชื่อมต่อ** ก่อนกด **บันทึกการตั้งค่า**

- Base URL รับเฉพาะ `127.0.0.1`, `localhost` หรือ `::1` เพื่อไม่ให้เอกสารถูกส่งออกนอกเครื่อง
- หน้าเว็บไม่แสดง API key เดิม; เว้นช่อง API key ว่างเพื่อเก็บค่าเดิม
- ค่าที่บันทึกลง `.env` มีผลกับงาน AI ใหม่ทันที

5. **ทดสอบความพร้อมของ OneOCR Wrapper (Smoke Test):**
   ```powershell
   python tests/smoke_test_oneocr.py
   ```
   หากขึ้น `OK` แสดงว่า DLL โหลดและอ่านภาษาไทยได้ถูกต้อง

---

## 3. การเริ่มต้นและหยุดการทำงานของระบบ (Start / Stop Operations)

### การเริ่มต้นระบบ (Start):
เปิด Command Prompt แล้วรันสคริปต์:
```cmd
.\run_server.cmd
```
หรือรันคำสั่ง:
```powershell
python -m src.server
```
หรือผ่าน Uvicorn โดยตรง:
```powershell
uvicorn src.server:app --host 127.0.0.1 --port 8000
```

เมื่อระบบพร้อมใช้งาน จะแสดงข้อความ:
```text
Starting Local Thai OCR API on 127.0.0.1:8000 (Localhost only: True)
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

เปิดเว็บเบราว์เซอร์ (Google Chrome หรือ Microsoft Edge) แล้วไปที่:
👉 **`http://127.0.0.1:8000/`**

### การหยุดระบบ (Stop):
- กด `Ctrl + C` ในหน้าต่าง Terminal ที่รันเซิร์ฟเวอร์
- หรือเปิด Command Prompt ในโฟลเดอร์โครงการแล้วรัน:
  ```cmd
  .\stop_server.cmd
  ```
- การกด `Ctrl + C` จะทำ Graceful Shutdown; ส่วน `stop_server.cmd` ใช้หยุด process และ subprocess ทันที จึงควรรอให้งาน OCR ปัจจุบันเสร็จก่อน

---

## 4. นโยบายการเก็บรักษาและล้างข้อมูล (Data Retention & Cleanup Policy)

เพื่อความปลอดภัยและความเป็นส่วนตัวของเอกสาร ระบบมีนโยบาย Retention ดังนี้:

1. **จุดเริ่มนับอายุเอกสาร (Age Calculation Origin):**
   - นับจากเวลา `updated_at` ล่าสุดของงานที่สิ้นสุดแล้ว (สถานะ `completed`, `partial`, `failed`, `cancelled`)
2. **ระยะเวลาจัดเก็บ (TTL):**
   - ค่าเริ่มต้นคือ 24 ชั่วโมง (`86400` วินาที) สามารถปรับแต่งได้ผ่านตัวแปร `RETENTION_SECONDS` ใน `.env`
3. **การปกป้องงานที่กำลังทำ (Active In-Progress Protection):**
   - งานที่อยู่ในสถานะ `running` หรือ `queued` จะได้รับการยกเว้นจาก retention cleanup แม้อายุจะเกินเวลา รวมถึงงานที่ HTML AI ยัง active; ปุ่มลบงานทั้งหมดใช้กฎแยกต่างหาก
4. **การประสานงานกับ Worker (Worker Coordination & Anti-Resurrection):**
   - Worker จะตรวจสอบสถานะก่อนประมวลผลแต่ละหน้าและก่อนประกอบไฟล์สรุป หากงานถูกลบไประหว่างทำงาน Worker จะยุติทันที และ**ไม่สร้างไดเรกทอรีหรือไฟล์กลับคืนมา (No resurrection)**
5. **การเรียกสั่งล้างข้อมูลด้วยตนเอง:**
   - สั่งล้างงานที่หมดอายุ: `POST /api/admin/cleanup` (สามารถระบุ `?max_age_seconds=3600` ได้)
   - สั่งลบทุกงาน: `DELETE /api/admin/jobs` ยกเลิก queued/running OCR ก่อนลบ ไม่จำกัดจำนวนงาน; หาก AI lock ไม่ว่างคืน 409 และรายงาน `failed_jobs` เมื่อไฟล์บางงานลบไม่ได้
   - สั่งลบงานเจาะจง: `DELETE /api/jobs/{job_id}`

---

## 5. การวินิจฉัยและแก้ไขข้อผิดพลาด (Troubleshooting & Error Diagnosis)

| อาการ / ข้อผิดพลาด | สาเหตุที่เป็นไปได้ | แนวทางแก้ไข |
|---|---|---|
| **`OSError: [WinError 193] %1 is not a valid Win32 application`** | ติดตั้ง Python แบบ 32-bit บนระบบ แต่ OneOCR DLL เป็น 64-bit | ถอนการติดตั้ง Python 32-bit แล้วติดตั้ง Python 64-bit (x64) |
| **`FileNotFoundError: Could not find oneocr.dll`** | วางไฟล์ DLL ไม่ถูกโฟลเดอร์ หรือขาดไฟล์ `onnxruntime.dll` | ตรวจสอบว่าในโฟลเดอร์ `oneOCR/` มีไฟล์ทั้ง 3 ไฟล์ครบถ้วน |
| **`HTTP 422: PDF มีรหัสผ่าน ไม่รองรับในรุ่นแรก`** | ผู้ใช้อัปโหลด PDF ที่ถูกล็อกด้วยรหัสผ่าน | ปลดรหัสผ่านออกจากไฟล์ PDF ก่อนอัปโหลดเข้าระบบ |
| **`HTTP 409 Conflict (ข้อขัดแย้งการแก้ไข)`** | มีการเปิดเอกสารหน้าเดียวกันในหลายแท็บ และบันทึกทับฉบับที่เก่ากว่า | กดปุ่ม "โหลดฉบับล่าสุด" ในหน้าต่างแจ้งเตือนเพื่อดึงข้อความล่าสุด |
| **`HTTP 503: Database lock timeout`** | ฐานข้อมูล SQLite กำลังถูกเขียนพร้อมกันและหมดเวลารอ (busy timeout) | ระบบจะส่งหัวข้อ `Retry-After: 1` ให้รันคำขอใหม่อีกครั้ง ข้อมูลจะไม่สูญหาย |
| **`HTTP 403 Forbidden: Access denied`** | พยายามเข้าใช้งานจาก IP ภายนอกที่ไม่ใช่ Loopback | ระบบจำกัดการเข้าถึงเฉพาะเครื่อง Localhost (`127.0.0.1`) เท่านั้น |
| **`Local AI Status: Offline`** | ยังไม่ได้เปิด Local LLM Server (เช่น LM Studio หรือ Ollama) | ระบบสามารถทำงานในโหมด "OCR อย่างเดียว" ได้สมบูรณ์ หากต้องการใช้ AI ให้เปิด Local LLM Server ที่พอร์ต 1234 |

---

## 6. ข้อจำกัดที่ทราบของระบบ (Known Limitations)

1. **ขอบเขตชุดข้อมูลทดสอบ:** ได้รับการรับรองและปรับระบบกับชุดข้อมูลทางการ 44 หน้า (`01.pdf`–`04.pdf`, `01.png`, `02.png`); เอกสารชุดขยาย (`05.pdf`–`07.pdf`) อยู่ในขอบเขตการทดสอบความทนทานและการดึงข้อความ
2. **เอกสารลายมือ:** ระบบมุ่งเน้นตัวพิมพ์ไทยและอังกฤษเป็นหลัก; เอกสารลายมือเขียนถือเป็นงานทดลอง
3. **การจัดรูปแบบตาราง:** ข้อความตารางที่ส่งออกเป็น `.txt` ใช้เครื่องหมาย Tab (`\t`) คั่นคอลัมน์ ไม่รับประกันการจัดวางหน้าตาเสมือน PDF ต้นฉบับ
4. **PDF มีรหัสผ่าน:** ไม่รองรับในรุ่นแรก ระบบจะปฏิเสธไฟล์และแจ้งเตือนทันทีโดยไม่เก็บไฟล์
5. **รูปแบบไฟล์ JPG:** ในชุดข้อมูลที่อนุมัติไม่มีไฟล์นามสกุล `.jpg` จึงถือว่าการรองรับ JPG เป็นงานเชิงฟังก์ชัน ยังไม่มีผลทดสอบคุณภาพ OCR บน JPG จริง


## 7. HTML AI, EPUB และ UI ปัจจุบัน

- UI minimal ใช้ Light เป็นค่าเริ่มต้น มี Dark theme และ icon ปุ่ม; ปุ่มลบไฟล์ตัวอักษรสีขาว
- HTML AI ทำงานใน background thread มี progress ทุก 2 วินาที: batch, stage, เวลา, timeout และ error พร้อมยกเลิก/ลองใหม่
- Refresh เบราว์เซอร์ดูงานเดิมต่อได้; restart server ไม่ resume งาน AI ต้องเริ่มใหม่ การยกเลิกรอ request ปัจจุบันจบ
- HTML AI แบ่งไม่เกิน 25 units ต่อ batch; LM Studio ที่รองรับจะปิด reasoning เฉพาะงานนี้เพื่อหลีกเลี่ยง timeout และใช้ basic.html เมื่อไม่สำเร็จ
- EPUB ต้องสร้าง XHTML preview ปัจจุบันก่อน กดสร้างไฟล์แล้วดาวน์โหลด `.epub` อัตโนมัติ พร้อมลิงก์ดาวน์โหลดซ้ำ
- `304 Not Modified` ของ static assets หมายถึง cache ใช้งานได้ ไม่ใช่ error การลบงาน
- แก้ Backend ให้ stop/start server; แก้ Frontend ให้ Ctrl+F5
- ดู architecture, workflow และ API ปัจจุบันใน [README](readme.md#สถาปัตยกรรมและแผนภาพการทำงาน-architecture--diagrams)

## 8. การส่งออก EPUB พร้อมรูปปก

1. เปิดงาน → HTML → สร้าง/บันทึก HTML ต้นทาง
2. EPUB → เลือกต้นทางและแบ่งบท กรอก metadata/วันที่/รหัสหนังสือ; เว้นรหัสให้ระบบสร้างได้
3. เลือก PNG/JPEG ไม่เกิน 2 MB ใส่ข้อความแทนรูป หรือเลือกสร้างแบบไม่มีปก
4. สร้าง XHTML Quick Preview แล้วตรวจสารบัญ/บทและ source revision
5. กดสร้างไฟล์ EPUB เพื่อดาวน์โหลดอัตโนมัติ; ถ้า source/config เปลี่ยนให้สร้าง Preview ใหม่

ระบบเก็บปกเดิมหลัง refresh และใช้ซ้ำเมื่อ regenerate; ไม่จำเป็นต้องเลือกไฟล์ใหม่ หากต้องการเอาปกออกให้เลือกสร้างแบบไม่มีปก

Generation ของ job เดียวกันชนกันคืน 409 และ cleanup/delete ข้ามหรือปฏิเสธงานที่กำลังอ่าน/เขียน EPUB ดาวน์โหลดใช้ snapshot จึงไม่ขาดกลางทางเมื่อ job ถูกลบภายหลัง รอบที่ validator ไม่ผ่านจะคง package พร้อมใช้เดิม

ผลตรวจรับและขอบเขตชุดข้อมูลดู [Phase 8 evidence](phase8/evidence.md)


## ขอบเขต Phase 8–9 ที่ใช้ร่วมกัน

Phase 8 ดูแล EPUB pipeline, XHTML Preview และรูปปก ส่วน Phase 9 เพิ่มการแก้สารบัญด้วยมือ, `toc.json` และ stable targets โดยใช้ exporter/validator/ปกเดิม Implementation ผ่านแล้ว

ปกคง input สูงสุด 2 MB / 16 megapixels และ canonical PNG สูงสุด 8 MB ใช้ preview payload และ API เดิม Phase 9 เพิ่ม thumbnail, drag-and-drop และรายละเอียดไฟล์ โดยไม่เพิ่ม storage/API ปกอีกชุด

Phase 9 รวม `toc_revision` ใน preview config งานเก่าไม่มี `toc.json` ใช้สารบัญอัตโนมัติได้ ผลตรวจรับดู [checklist](checklist.md#phase-9--แก้ไขสารบัญ-epub-และ-stable-targets-editable-epub-toc) และ [หลักฐาน](phase9/evidence.md)

## Phase 9 — แก้ไขสารบัญ EPUB

1. เปิดงาน → แท็บ `EPUB` → กด `โหลดสารบัญ`
2. แก้ชื่อ เลื่อนขึ้น/ลง ปรับระดับ 1–3 เพิ่ม/เอารายการออก หรือเลือก target จากหัวข้อ/ต้นบท
3. กด `ดู` เพื่อตรวจตำแหน่งใน Quick Preview
4. ถ้ามี unresolved ให้เลือก target ใหม่ก่อน
5. กด `บันทึกสารบัญและอัปเดต Preview`
6. ตรวจ Preview แล้วกด `สร้างไฟล์ EPUB`

ถ้า HTML หรือ config เปลี่ยน ระบบให้ re-match และแสดง matched/unresolved โดยไม่ทับ draft เงียบ ๆ การยกเลิก re-match คง draft เดิม สองแท็บแก้พร้อมกันคืน 409 ให้โหลด revision ล่าสุดก่อนบันทึกใหม่

รูปปกลากมาวางในพื้นที่ปกหรือใช้ file picker ได้ thumbnail ที่ระบุ `ยังไม่บันทึก` เป็น draft; ต้องสร้าง Preview ใหม่จึงจะเป็นปกของ package

## Phase 10 — Document Translation (วางแผน)

วางแผนรองรับการเลือกภาษาปลายทางและ style `ทั่วไป`, `นิยาย`, `วิชาการ`, `ราชการ` ผ่าน Google Cloud Translation, Local AI หรือ Hybrid ฟีเจอร์นี้ยังไม่เริ่ม implementation และยังไม่มีเมนูใช้งาน

ทุก style ไม่บังคับแปลทุกคำ ศัพท์เฉพาะทาง ชื่อเทคโนโลยี ชื่อผลิตภัณฑ์ ตัวย่อ หรือคำที่แปลแล้วทำให้ความหมายคลาดเคลื่อน สามารถคงคำเดิมหรือใช้คำทับศัพท์ได้ โดยควรกำหนดใน glossary/do-not-translate เพื่อให้ใช้สม่ำเสมอทั้งเอกสาร

ชุดทดสอบที่ล็อกไว้คือ `demo/08.pdf`–`13.png`: ตารางอังกฤษ, ภาพจีน+อังกฤษที่มีศัพท์เฉพาะ, นิยายอังกฤษสองภาพ, หนังสือสอน IT และหนังสือสอน IT ที่มี code program ชุดนี้ยังรอ ground truth และยังไม่ครอบคลุมเอกสารราชการ

Google/Hybrid จะส่งข้อความออกจากเครื่องและต้องให้ผู้ใช้ยืนยันก่อนเริ่ม ส่วน Local AI จะคงโหมดไม่มี external request ผลแปลต้องผ่านหน้าตรวจ diff และ validator ก่อนส่งออก Text/HTML/EPUB ดูขอบเขตใน [Phase 10 checklist](checklist.md#phase-10--แปลเอกสารหลายภาษาและเลือกรูปแบบการแปล-document-translation)

## Phase 8.1 — Structured OCR

เปิดงาน OCR → แท็บ `Structured OCR` → `สร้าง Structured Text / HTML` ระบบใช้ artifact เดิมโดยไม่ OCR หรือเรียก Local AI ซ้ำ เลือกหน้า ซูม และคลิก cell/block เพื่อไฮไลต์ตำแหน่งบนต้นฉบับได้

เมนูผลลัพธ์สลับ `Structured HTML`, `OCR ต้นฉบับ`, `ข้อความ AI แก้ไข` และ `ข้อความฉบับผู้ใช้` ได้ พร้อมดาวน์โหลด Text, HTML และ layout.json ถ้าข้อความต้นทางเปลี่ยน ระบบซ่อน download และขึ้นสถานะล้าสมัย ให้กดสร้าง Structured ใหม่ก่อน

ต้องการ EPUB ที่รักษาตาราง: ไปแท็บ EPUB เลือกต้นทาง `Structured HTML` แล้วสร้าง XHTML Quick Preview ก่อน package ถ้า structured source เปลี่ยน ระบบจะบล็อก package เก่า

ระบบรองรับ PDF vector table และภาพสแกนที่มีเส้นตาราง งานที่ไม่มี bbox หรือ private-use glyph ที่ตีความไม่ได้จะแสดง unresolved เพื่อให้ตรวจเอง ผล automated acceptance ผ่านแล้ว; ยังรอเจ้าของงานยืนยัน ground truth ด้วยคน ดู [checklist](checklist.md#phase8-1) และ [หลักฐาน](phase8_1/evidence.md)

## 9. การแก้ไขสารบัญ EPUB และ Stable Targets (Phase 9)

1. เปิดงาน → แท็บ `EPUB` → ส่วน **แก้ไขสารบัญ**
2. กดปุ่ม **โหลดสารบัญ** เพื่อดึงโครงสร้างสารบัญปัจจุบันหรือสร้างอัตโนมัติจากหัวข้อ `h1`–`h3` และต้นบท
3. ปรับแต่งสารบัญ:
   - **แก้ไขชื่อ (Label):** พิมพ์ชื่อสารบัญที่ต้องการแสดง
   - **ปรับระดับ (Level 1–3):** ใช้ปุ่มย่อหน้าเพื่อจัดระดับชั้นหัวข้อย่อย
   - **ย้ายลำดับ (Reorder):** เลื่อนลำดับรายการขึ้นหรือลง
   - **เลือกปลายทาง (Target):** เลือกตำแหน่งที่ต้องการให้คลิกลิงก์ไปถึง (ต้นบทหรือหัวข้อต่างๆ)
   - **เพิ่ม/ลบรายการ:** เพิ่มหัวข้อสารบัญใหม่ หรือลบรายการที่ไม่ต้องการในสารบัญออก โดยไม่กระทบเนื้อหาหนังสือจริง
4. กด **บันทึกสารบัญและอัปเดต Preview** เพื่อคำนวณ `toc_revision` และรีเฟรช XHTML Quick Preview
5. หากเนื้อหา HTML ต้นทางมีการแก้ไข ระบบจะแจ้งเตือน Stale และทำการ Re-match หัวข้อให้อัตโนมัติ โดยรายการที่ไม่พบบนหน้าจะแสดงสถานะ `unresolved` ชัดเจน
6. กด **สร้างไฟล์ EPUB** เพื่อแพ็กเกจหนังสือพร้อมสารบัญฉบับกำหนดเอง

