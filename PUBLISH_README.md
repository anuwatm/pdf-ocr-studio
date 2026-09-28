# Local Thai OCR Web — ชุดติดตั้ง

โฟลเดอร์นี้ย้ายไป Windows 10/11 แบบ 64-bit ได้ทั้งก้อน โดยมี OneOCR DLL/model, backend, หน้าเว็บ และไฟล์ตัวอย่าง `demo/` ครบแล้ว

ไม่รวม `.env`, `venv/`, `data/jobs.db` และไฟล์เอกสาร/ผลลัพธ์ของเครื่องต้นทาง เพื่อไม่ย้ายค่า Local LLM หรือข้อมูลผู้ใช้ไปด้วย

## ติดตั้ง

1. ติดตั้ง Python 3.10+ แบบ 64-bit และเลือกติดตั้ง Python Launcher (`py`)
2. เปิด PowerShell ที่โฟลเดอร์นี้
3. หาก PowerShell บล็อก script ชั่วคราว ให้รัน `Set-ExecutionPolicy -Scope Process Bypass`
4. รัน `./run_server.ps1` ได้เลย; script จะติดตั้งครั้งแรกให้อัตโนมัติ หรือรัน `./install.ps1` / `install.cmd` แยกก่อนก็ได้
5. เปิด `http://127.0.0.1:8000/`

## Local AI

เปิด `http://127.0.0.1:8000/config.html` แล้วตั้งค่า Base URL, Model, API key และ Timeout ของ Local LLM. Base URL รับเฉพาะ `127.0.0.1`, `localhost` หรือ `::1`.

## โครงสร้าง

| รายการ | หน้าที่ |
|---|---|
| `src/` | FastAPI, worker, OCR และ AI correction |
| `static/` | หน้าเว็บ upload, progress, review, config |
| `oneOCR/` | OneOCR DLL, model และ runtime |
| `files/` | ต้นฉบับที่อัปโหลดและผลลัพธ์ของงาน |
| `data/` | SQLite job database |
| `demo/` | เอกสารตัวอย่างสำหรับตรวจสอบ |

การแปลง PDF: หน้าเว็บอ่านจำนวนหน้าก่อนเริ่ม แล้วเลือก OCR จากหน้า 1 ได้สูงสุด 100 หน้าต่อครั้ง. เมื่อเลือก AI ผลลัพธ์มี `raw.txt` และ `corrected.txt` แยกกัน.
