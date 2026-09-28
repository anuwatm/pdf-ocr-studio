# คู่มือการติดตั้ง เริ่ม/หยุดระบบ ตรวจสอบข้อผิดพลาด และข้อจำกัด (System Operations Manual)

**โครงการ:** Local Thai OCR Web  
**เวอร์ชัน:** Phase 6 Final Delivery  
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
เปิด Terminal หรือ PowerShell แล้วรันสคริปต์:
```powershell
.\run_server.ps1
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
- ระบบจะทำ Graceful Shutdown อัตโนมัติ: ยุติการทำงานของ Worker Subprocess ที่กำลังทำงาน, บันทึกสถานะลงฐานข้อมูล SQLite, และปิดการเชื่อมต่อโดยไม่ทำให้ไฟล์เสียหาย

---

## 4. นโยบายการเก็บรักษาและล้างข้อมูล (Data Retention & Cleanup Policy)

เพื่อความปลอดภัยและความเป็นส่วนตัวของเอกสาร ระบบมีนโยบาย Retention ดังนี้:

1. **จุดเริ่มนับอายุเอกสาร (Age Calculation Origin):**
   - นับจากเวลา `updated_at` ล่าสุดของงานที่สิ้นสุดแล้ว (สถานะ `completed`, `partial`, `failed`, `cancelled`)
2. **ระยะเวลาจัดเก็บ (TTL):**
   - ค่าเริ่มต้นคือ 24 ชั่วโมง (`86400` วินาที) สามารถปรับแต่งได้ผ่านตัวแปร `RETENTION_SECONDS` ใน `.env`
3. **การปกป้องงานที่กำลังทำ (Active In-Progress Protection):**
   - งานที่อยู่ในสถานะ `running` หรือ `queued` จะได้รับการยกเว้นจากการลบเสมอ แม้อายุจะเกินเวลา
4. **การประสานงานกับ Worker (Worker Coordination & Anti-Resurrection):**
   - Worker จะตรวจสอบสถานะก่อนประมวลผลแต่ละหน้าและก่อนประกอบไฟล์สรุป หากงานถูกลบไประหว่างทำงาน Worker จะยุติทันที และ**ไม่สร้างไดเรกทอรีหรือไฟล์กลับคืนมา (No resurrection)**
5. **การเรียกสั่งล้างข้อมูลด้วยตนเอง:**
   - สั่งล้างงานที่หมดอายุ: `POST /api/admin/cleanup` (สามารถระบุ `?max_age_seconds=3600` ได้)
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
