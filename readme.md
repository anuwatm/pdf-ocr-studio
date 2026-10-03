# Local Thai OCR Web

[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011%20(64--bit)-0078D6.svg?logo=windows)](https://microsoft.com)
[![Python](https://img.shields.io/badge/Python-3.10%2B%20(64--bit)-3776AB.svg?logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688.svg?logo=fastapi)](https://fastapi.tiangolo.com)
[![Engine](https://img.shields.io/badge/OCR-OneOCR%20(ctypes)-critical.svg)](#จุดเด่นของระบบ-key-features)
[![Local AI](https://img.shields.io/badge/AI-Local%20LLM%20%2F%20VLM-blueviolet.svg)](#การตั้งค่า-local-ai-ตรวจแก้)
[![Security](https://img.shields.io/badge/Privacy-100%25%20Offline%20%2F%20Loopback-success.svg)](#จุดเด่นของระบบ-key-features)

เว็บแอปพลิเคชันสำหรับแปลงเอกสาร **PDF และภาพภาษาไทยเป็นข้อความ UTF-8** ขับเคลื่อนด้วย **OneOCR** (เอนจิน OCR ภาษาไทยแบบเนทีฟจาก Windows 11 Snipping Tool ผ่าน Python `ctypes`) พร้อมระบบจัดลำดับข้อความอัจฉริยะ (Smart Layout Assembly) และผสานพลัง **Local AI (LLM/VLM)** ช่วยตรวจแก้คำผิด สระ และวรรณยุกต์ โดยประมวลผล **ภายในเครื่อง 100% (Localhost Single-User)** โดยไม่ส่งข้อมูลออกนอกเครื่อง พร้อมหน้าเว็บ **Web Studio** สำหรับตรวจทาน เทียบภาพต้นฉบับ แก้ไข และส่งออกไฟล์

> [!IMPORTANT]
> ระบบรองรับ Windows 10/11 แบบ 64-bit เท่านั้น เพราะใช้ OneOCR DLL แบบ 64-bit และออกแบบให้ใช้งานจาก `127.0.0.1` บนเครื่องเดียว

## เริ่มใช้งานด่วนจาก GitHub

หลัง clone repository แล้ว ให้เปิด Command Prompt ที่โฟลเดอร์โครงการและรัน:

```cmd
.\run_server.cmd
```

สคริปต์จะสร้าง `venv` และติดตั้ง dependencies ให้เองในครั้งแรก จากนั้นเปิด [http://127.0.0.1:8000/](http://127.0.0.1:8000/) ในเบราว์เซอร์

หยุด server:

```cmd
.\stop_server.cmd
```


### โหมด OCR และ Local AI

- ค่าเริ่มต้นคือ **OneOCR อย่างเดียว (Baseline)** จึงใช้งาน OCR ได้แม้ไม่ได้เปิด Local LLM
- เลือกช่วงหน้าเริ่มต้น–สิ้นสุดได้ตามจำนวนหน้าของเอกสาร; ระบบแบ่งทำงานเป็น **batch ละ 200 หน้า** ต่อเนื่องจนจบช่วงที่เลือก
- ก่อนเริ่มงานเลือกได้ว่าจะใส่หัวข้อเลขหน้า เช่น `--- Page 1 ---` ในไฟล์ข้อความรวม (`raw.txt`, `corrected.txt`, `final.txt`) หรือไม่; ค่าเริ่มต้นคือใส่
- เลือก PDF แล้วระบบจะอัปโหลดและตรวจจำนวนหน้าทันที; งานที่ยกเลิกสามารถเริ่มต่อเฉพาะหน้าที่ยังไม่เสร็จได้
- เมื่อ OCR แต่ละหน้าเสร็จ หน้า Preview จะเปลี่ยนไปแสดงภาพและข้อความของหน้านั้นทันที
- เมื่อ Local AI เป็น Offline ระบบจะล็อก **OneOCR + Local AI ตรวจแก้คำ** ไว้
- กด **ทดสอบการเชื่อมต่อ** ข้างสถานะ Local AI; เมื่อเชื่อมต่อและพบโมเดลแล้ว ตัวเลือก AI จะถูกปลดล็อก

---

## สารบัญ

- [เริ่มใช้งานด่วนจาก GitHub](#เริ่มใช้งานด่วนจาก-github)
- [จุดเด่นของระบบ (Key Features)](#จุดเด่นของระบบ-key-features)
- [สถาปัตยกรรมและแผนภาพการทำงาน (Architecture & Diagrams)](#สถาปัตยกรรมและแผนภาพการทำงาน-architecture--diagrams)
  - [1. แผนภาพสถาปัตยกรรมระบบและการแยก Process](#1-แผนภาพสถาปัตยกรรมระบบและการแยก-process)
  - [2. แผนภาพการประมวลผลและการจัดเส้นทางเอกสาร (Intelligent Page Routing)](#2-แผนภาพการประมวลผลและการจัดเส้นทางเอกสาร-intelligent-page-routing)
  - [3. แผนภาพการตรวจแก้ด้วย Local AI และ Diff Engine](#3-แผนภาพการตรวจแก้ด้วย-local-ai-และ-diff-engine)
  - [4. แผนภาพวงจรสถานะงานและการกู้คืนข้อผิดพลาด (Job Lifecycle & Fault Tolerance)](#4-แผนภาพวงจรสถานะงานและการกู้คืนข้อผิดพลาด-job-lifecycle--fault-tolerance)
  - [5. แผนภาพขั้นตอนการทำงานของผู้ใช้บนหน้าเว็บ (End-to-End User Experience Flow)](#5-แผนภาพขั้นตอนการทำงานของผู้ใช้บนหน้าเว็บ-end-to-end-user-experience-flow)
- [การติดตั้งและเริ่มต้นใช้งาน (Getting Started)](#การติดตั้งและเริ่มต้นใช้งาน-getting-started)
  - [ความต้องการของระบบ](#ความต้องการของระบบ-prerequisites)
  - [ติดตั้งและเริ่มต้นใช้งาน](#การติดตั้งและเริ่มต้นใช้งาน-getting-started)
- [การตั้งค่า Local AI ตรวจแก้](#การตั้งค่า-local-ai-ตรวจแก้)
- [สัญญาข้อมูลและไฟล์ผลลัพธ์ (Data Contract)](#สัญญาข้อมูลและไฟล์ผลลัพธ์-data-contract)
- [รายละเอียด REST API (API Reference)](#รายละเอียด-rest-api-api-reference)
- [โครงสร้างโฟลเดอร์ (Repository Structure)](#โครงสร้างโฟลเดอร์-repository-structure)
- [ผลการทดสอบและเกณฑ์ตรวจรับ (Verification & Benchmarks)](#ผลการทดสอบและเกณฑ์ตรวจรับ-verification--benchmarks)
- [ข้อควรรู้ก่อนเผยแพร่บน GitHub](#ข้อควรรู้ก่อนเผยแพร่บน-github)

---

## จุดเด่นของระบบ (Key Features)

1. **OneOCR ภาษาไทยแท้ (High Accuracy OCR):**
   - โหลดโมเดล `oneocr.dll` และ `oneocr.onemodel` ผ่าน Python `ctypes` โดยตรง ไม่ต้องติดตั้งโปรแกรม C++ เพิ่มเติม
   - อัตราความผิดพลาดต่ำมาก (**CER 0.04%** บนเอกสารไทยตัวพิมพ์ชัด และ **CER รวม 0.83%** บนชุดตรวจรับ)
2. **Hybrid PDF Pipeline (ตรวจจับและจัดเส้นทางอัจฉริยะ):**
   - แยกแยะหน้าเอกสารอัตโนมัติ: ดึง Text Layer ตรงจาก Digital PDF ที่สมบูรณ์ หรือเรนเดอร์ภาพความละเอียดสูงเพื่อทำ OCR สำหรับหน้าสแกน/ภาพ
   - ตรวจจับหน้าว่างจริง (`blank`) ไม่ทิ้งหน้าและไม่แสดงเป็นข้อความว่างลึกลับ
3. **Interactive Dual-Pane Web Studio:**
   - หน้าจอทำงานแบบแยก 2 ฝั่ง (ต้นฉบับ vs ข้อความที่แปลงได้)
   - **Bidirectional Bounding Box Sync:** คลิกคำ/บรรทัดบนข้อความ กรอบสีบนภาพต้นฉบับจะเลื่อนและไฮไลต์ตำแหน่งทันที และสามารถคลิกกรอบบนภาพเพื่อวิ่งไปยังข้อความได้เช่นกัน
   - แสดงหน้า Preview ที่เพิ่ง OCR เสร็จระหว่างงานทำงาน โดยไม่สลับหน้าหากมีข้อความแก้มือที่ยังไม่บันทึก
4. **Local AI Correction & Diff Engine:**
   - เริ่มต้นเป็น OneOCR only; เปิด AI ได้เมื่อทดสอบการเชื่อมต่อ Local LLM ผ่านแล้ว
   - ใช้กฎ deterministic สำหรับ OCR ที่แยก `ำ` เป็น ` า` หรือ ` ้า` ก่อนส่งคำที่เหลือให้ Local LLM เสนอการแก้
   - ปุ่ม **AI ตรวจคำผิดทั้งหมด** อ่าน `raw.txt` ของทุกหน้าที่ OCR สำเร็จแล้ว โดยไม่ทำ OCR ซ้ำ และเก็บผลเป็นข้อเสนอ
   - ปุ่ม **Accept / Revert** ทีละจุด หรือทั้งหมด พร้อมการันตีคืนค่า raw text byte-for-byte ได้ 100%
5. **Crash Isolation & Resilient Architecture:**
   - แยก **FastAPI Web Server** ออกจาก **OCR Worker Subprocess** อย่างเด็ดขาด ป้องกัน Native DLL Crash ไม่ให้เซิร์ฟเวอร์หลักหยุดทำงาน
   - จัดการคิวงานด้วย SQLite โหมด Write-Ahead Logging (WAL) พร้อมกู้คืนงานที่ค้าง (`recovering interrupted jobs`) หลังเปิดระบบใหม่
   - กลไกป้องกันการแก้ไขชนกันหลายแท็บ (Multi-tab Conflict Detection ด้วย ETag/Revision คืนค่า HTTP 409)
6. **Data Retention & Anti-Resurrection:**
   - หน้า **งาน OCR ก่อนหน้า** เปิดดู ดาวน์โหลด หรือลบงานทีละรายการได้ และลบงานที่เก่ากว่าจำนวนวันที่ผู้ใช้กำหนดได้
   - ป้องกันสภาวะ Race Condition: หากงานถูกลบไปแล้ว Worker จะยุติการเขียนไฟล์กลับคืนทันที (0 Resurrection)
7. **ความเป็นส่วนตัวและ Offline 100%:**
   - เซิร์ฟเวอร์ผูกเข้ากับ `127.0.0.1` (Loopback Only) ปฏิเสธการเข้าถึงจาก IP ภายนอกด้วย HTTP 403 Forbidden
   - ประมวลผลและเก็บข้อมูลบนเครื่องของผู้ใช้เท่านั้น ไม่ส่งข้อมูลใด ๆ ออกนอกเครือข่าย
8. **ส่งออกผลลัพธ์และภาพ PDF:**
   - ดาวน์โหลด `raw.txt`, `corrected.txt`, `final.txt` และ ZIP ผลลัพธ์ได้ แม้งานถูกยกเลิก โดยระบบคงข้อความหน้าที่ทำสำเร็จแล้วไว้
   - สำหรับไฟล์ PDF สามารถกด **"ดาวน์โหลดภาพแต่ละหน้า (ZIP)"** ได้ทันทีในแท็บอัปโหลดเอกสาร (PNG 200 DPI ตามช่วงหน้าที่เลือก) โดยไม่ต้องสั่งเริ่มทำ OCR
9. **EPUB 3 Export และ XHTML Quick Preview (Phase 8):**
   - เลือก `basic.html`, `ai.html` หรือ `final.html` เป็นฐาน แล้วตรวจ XHTML Quick Preview พร้อมโครงสร้างสารบัญก่อนสร้างไฟล์ `.epub`
   - EPUB 3 แบบ reflowable มีสารบัญ, metadata, CSS ภาษาไทยภายในไฟล์, ระบบตรวจจับ stale revision และ internal package validator ตรวจสอบความถูกต้อง
10. **สตูดิโอแยก 5 แท็บการทำงาน และ Visual Editor แบบ Word (ใหม่):**
    - แยกพื้นที่ทำงานเป็น 5 แท็บอิสระ: **อัปโหลดเอกสาร**, **ผลข้อความ**, **HTML**, **ส่งออก EPUB**, และ **งาน OCR ก่อนหน้า**
    - ในแท็บ HTML มีระบบแก้ไขสองโหมด: **CodeMirror 5.65.21** สำหรับแก้ไขโค้ด HTML โดยตรง และ **Visual Editor แบบ Word** (WYSIWYG: ตัวหนา, ตัวเอียง, ขีดเส้นใต้, หัวข้อ H1–H3, รายการจุด/ตัวเลข, ลิงก์, Undo/Redo) พร้อมซิงก์สองฝั่งอัตโนมัติ
    - ระบบบันทึกแบบแมนนวล (Ctrl+S / ปุ่มบันทึก ปราศจาก Autosave) ป้องกันข้อผิดพลาด draft สูญหาย รองรับ Revision Conflict (HTTP 409) และแก้ปัญหา Title leak (`OCR Document - ...`) ไม่ให้ปนเปื้อนลงใน `<body>`

---

## สถาปัตยกรรมและแผนภาพการทำงาน (Architecture & Diagrams)

ส่วนนี้อธิบายเส้นทางข้อมูลที่ใช้งานจริงในรุ่นปัจจุบัน: งาน OCR ทำใน Worker แยก process, ผลลัพธ์เขียนลงดิสก์ทีละหน้า, พื้นที่ทำงานแยกเป็น 5 แท็บอิสระ, และหน้าเว็บอ่านสถานะจาก API เพื่อแสดงความคืบหน้าทันที

### 1. สถาปัตยกรรมระบบ

```mermaid
flowchart TB
    subgraph Browser ["Browser: 127.0.0.1 (Web Studio 5 แท็บ)"]
        Tab1["แท็บ 1: อัปโหลดเอกสาร<br/>เลือกช่วงหน้า / โหลดภาพ ZIP ทันที"]
        Tab2["แท็บ 2: ผลข้อความ<br/>Dual-Pane Sync / Accept-Revert / AI Full Check"]
        Tab3["แท็บ 3: HTML Studio<br/>CodeMirror 5.65.21 / Visual Editor แบบ Word<br/>Sandboxed Preview / Manual Save (Ctrl+S)"]
        Tab4["แท็บ 4: ส่งออก EPUB<br/>XHTML Quick Preview / Metadata Form / Packaging"]
        Tab5["แท็บ 5: งาน OCR ก่อนหน้า<br/>History / Status / Retention Cleanup"]
        Config["Config & Test Local LLM"]
    end

    subgraph Server ["FastAPI Web Server process"]
        API["REST API"]
        Templates["Template Partials Assembly<br/>(index + text + html + epub)"]
        Queue["Job Manager / Supervisor"]
        HtmlExport["Structured HTML Exporter"]
        EpubExport["XHTML Quick Preview<br/>EPUB 3 Packager + Validator"]
        Sanitizer["Strict Allowlist Sanitizer<br/>(Title & Head Discard from Body)"]
        AILock["Local AI Coordination<br/>(จำกัดครั้งละ 1 งาน)"]
        Cleanup["History & Retention Cleanup"]
    end

    subgraph Worker ["OCR Worker Subprocess"]
        Runner["worker_process.py"]
        Pipeline["pipeline.py"]
        OneOCR["OneOCR via ctypes (Native 64-bit)"]
    end

    subgraph LocalData ["ข้อมูลภายในเครื่อง (Local Storage)"]
        DB[("SQLite WAL (data/jobs.db)")]
        Files[("files/{job_id}/<br/>input, raw.txt, corrected.txt, final.txt,<br/>ocr.json, changes.json, page-images.zip")]
        ExportFiles[("files/{job_id}/export/<br/>basic.html, ai.html, final.html,<br/>epub/preview.xhtml, book.epub,<br/>export_meta.json, epub_meta.json")]
    end

    LLM["Local LLM (OpenAI-compatible)<br/>127.0.0.1 Loopback Only"]

    Tab1 --> API
    Tab2 <--> API
    Tab3 <--> API
    Tab4 <--> API
    Tab5 <--> API
    Config <--> API
    API --> Templates
    API <--> DB
    API <--> Files
    API --> HtmlExport
    API --> EpubExport
    HtmlExport --> Sanitizer
    HtmlExport --> EpubExport
    HtmlExport <--> ExportFiles
    EpubExport <--> ExportFiles
    HtmlExport --> AILock
    Runner -.->|OCR+AI active| AILock
    AILock <--> LLM
    API --> Queue --> Runner
    Runner <--> DB
    Runner --> Pipeline --> OneOCR
    Runner --> Files
    Cleanup --> DB
    Cleanup --> Files
    Cleanup --> ExportFiles
```

OneOCR DLL ถูกโหลดใน Worker process เท่านั้น ดังนั้นความขัดข้องของ native OCR ไม่ทำให้ FastAPI process หยุดตามไปด้วย. API สามารถสร้าง ZIP ภาพ PDF (200 DPI) ให้ดาวน์โหลดได้ทันทีจากแท็บอัปโหลดโดยไม่ต้องรัน OCR. และทั้ง API กับ Local LLM ถูกจำกัดการเชื่อมต่อไว้ที่ loopback (127.0.0.1) เท่านั้น.

---

### 2. เส้นทาง OCR, batch, Preview และการดาวน์โหลดภาพ ZIP

```mermaid
flowchart TD
    Upload(["เลือก PDF / PNG / JPG"]) --> Pdf{"เป็น PDF หรือไม่?"}
    Pdf -->|PDF| Count["อัปโหลดและอ่านจำนวนหน้าทันที"]
    Pdf -->|ภาพ| ImageOne["กำหนดเป็น 1 หน้า"]
    Count --> ChooseOption{"ผู้ใช้ต้องการทำสิ่งใด?"}
    ChooseOption -->|ดาวน์โหลดภาพ PDF ทันที| ZipNow["กด 'ดาวน์โหลดภาพแต่ละหน้า (ZIP)'<br/>(ไม่ต้องเริ่ม OCR)"]
    ZipNow --> RenderZip["เรนเดอร์ PNG 200 DPI ตามช่วงหน้า<br/>ส่งออก page-images.zip"]
    RenderZip --> DoneZip(["ดาวน์โหลด ZIP สำเร็จ"])
    ChooseOption -->|เริ่มประมวลผล OCR| Choose["เลือกช่วงหน้าเริ่มต้น-สิ้นสุด"]
    ImageOne --> Choose
    Choose --> Start["สร้างงานและเข้าคิว"]
    Start --> Batch["Worker แบ่งช่วงที่เลือกเป็น batch ละ 200 หน้า"]
    Batch --> Page["ประมวลผลหน้าถัดไป"]
    Page --> Blank{"หน้าว่างหรือไม่?"}
    Blank -->|ใช่| SaveBlank["บันทึก blank"]
    Blank -->|ไม่ใช่| Route{"มี PDF Text Layer ที่ใช้ได้หรือไม่?"}
    Route -->|ใช่| Extract["สกัดข้อความจาก PDF Text Layer"]
    Route -->|ไม่ใช่ / เป็นภาพ| OCR["เรนเดอร์ภาพและเรียก OneOCR"]
    Extract --> Normalize["จัดลำดับข้อความ และ normalize รูปแบบที่ยืนยันได้"]
    OCR --> Normalize
    Normalize --> Save["เขียน raw.txt และ ocr.json แบบ UTF-8"]
    SaveBlank --> Update["อัปเดต SQLite"]
    Save --> Update
    Update --> Preview["หน้าเว็บแสดงสถานะและ Preview หน้าที่เสร็จทันที"]
    Preview --> More{"มีหน้าถัดไป?"}
    More -->|มี| Page
    More -->|ไม่มี| Assemble["รวม raw.txt, corrected.txt และ final.txt"]
    Assemble --> Finish(["OCR เสร็จสมบูรณ์"])
    Finish --> ExportReady["พร้อมส่งออก basic/ai/final HTML<br/>และสร้าง XHTML Quick Preview / EPUB"]
```

PDF จะตรวจจำนวนหน้าทันทีหลังเลือกไฟล์เพื่อให้เลือกช่วงหน้าหรือดาวน์โหลดภาพ ZIP ได้ทันที. ช่วงหน้าที่เลือกอาจยาวกว่า 200 หน้าได้; Worker จะทำต่อเนื่องเป็น batch ละ 200 หน้าเพื่อคืนทรัพยากร OCR ระหว่าง batch. เมื่อหน้าใดเสร็จ ระบบจะเขียนไฟล์และอัปเดตสถานะก่อนเริ่มหน้าถัดไป ทำให้ Preview แสดงผลหน้านั้นได้ทันที.

---

### 3. Baseline, Local AI, HTML Studio (Code vs Visual) และการตรวจทาน

```mermaid
flowchart TD
    Raw[("raw.txt จากแต่ละหน้า")] --> Rule["กฎ deterministic<br/>เช่น อักษร + ช่องว่าง + า/วรรณยุกต์+า"]
    Rule --> Baseline["OneOCR Baseline ที่ normalize แล้ว"]
    Baseline --> Mode{"เลือก Local AI หรือไม่?"}
    Mode -->|ไม่เลือก| FinalRaw["สร้าง final.txt จากข้อความ baseline"]
    Mode -->|เลือก| Detect["Prescreener หาเฉพาะจุดน่าสงสัย"]
    Detect --> Prompt["สร้าง prompt และเรียก Local LLM ผ่าน loopback"]
    Prompt --> Response{"ตอบ JSON ที่อ่านได้หรือไม่?"}
    Response -->|ไม่| Safe["คงข้อความ baseline และบันทึกสถานะ AI failed/partial"]
    Response -->|ใช่| Validate["ตรวจ exact substring, ตำแหน่ง, block mapping และ edit distance"]
    Validate --> Proposals["บันทึก changes.json และ corrected.txt"]
    Safe --> FinalRaw
    Proposals --> FinalRaw
    FinalRaw --> Review["ผู้ใช้ตรวจใน Web Studio (แท็บ ผลข้อความ)"]
    Review --> Accept["Accept ข้อเสนอ / แก้มือ แล้วบันทึก final.txt"]
    Review --> Revert["Revert หรือไม่แก้: คง final.txt เดิม"]
    Review -.-> FullAI["AI ตรวจคำผิดทั้งหมด: อ่าน raw.txt ทุกหน้าที่ OCR สำเร็จ<br/>ทีละหน้า โดยไม่ทำ OCR ซ้ำ"]
    FullAI --> Prompt
    Accept --> SavedFinal["final.txt ที่ผู้ใช้ควบคุม"]
    Revert --> SavedFinal

    SavedFinal --> HtmlTab["เข้าสู่ แท็บ HTML (HTML Studio)"]
    HtmlTab --> HtmlMode{"ส่งออก HTML เริ่มต้นแบบใด?"}
    HtmlMode -->|basic| BasicHTML["สร้าง basic.html แบบ deterministic"]
    HtmlMode -->|ai| HtmlAILock{"Local AI ว่างหรือไม่?"}
    HtmlAILock -->|ไม่ว่าง| Conflict["HTTP 409 ให้ลองใหม่ภายหลัง"]
    HtmlAILock -->|offline| BasicFallback["คง basic.html และบันทึก locked_ai_offline"]
    HtmlAILock -->|ว่างและพร้อม| Semantic["Local LLM เสนอ semantic tags"]
    Semantic --> HtmlValidate{"annotation ผ่าน validator หรือไม่?"}
    HtmlValidate -->|ผ่าน| AIHTML["สร้าง ai.html"]
    HtmlValidate -->|ไม่ผ่าน| BasicFallback

    BasicHTML --> EditorWorkspace["พื้นที่แก้ไข HTML"]
    AIHTML --> EditorWorkspace
    BasicFallback --> EditorWorkspace

    subgraph DualEditor ["ระบบแก้ไขสองโหมด (Dual-Mode Editor)"]
        CodeView["CodeMirror 5.65.21<br/>(แก้ไขโค้ด HTML โดยตรง)"]
        VisualView["Visual Editor แบบ Word<br/>(WYSIWYG: Bold/Italic/H1-H3/Lists/Links)"]
        CodeView <--> VisualView
    end

    EditorWorkspace --> DualEditor
    DualEditor --> LivePreview["Sandboxed Preview Iframe<br/>(CSP ปลอดภัย อัปเดต debounce 350ms)"]
    DualEditor --> ManualSave["กดบันทึก Final HTML หรือ Ctrl+S/Cmd+S"]
    ManualSave --> RevCheck{"ตรวจ base_revision conflict หรือไม่?"}
    RevCheck -->|ชน 409 Conflict| RevModal["แจ้งเตือน Revision Conflict<br/>ยืนยัน Overwrite หรือยกเลิก"]
    RevModal -->|ยกเลิก| DualEditor
    RevModal -->|ยืนยัน| SanitizeEngine
    RevCheck -->|ไม่ชน| SanitizeEngine["StrictHtmlSanitizer<br/>- กรอง Active content / Unsafe links<br/>- ตัด Head และ Title ออกจาก Body (ป้องกัน Title Leak)"]
    SanitizeEngine --> FinalHTML["บันทึก final.html ลงดิสก์"]

    FinalHTML --> EpubSource["ส่งต่อไปยัง แท็บ ส่งออก EPUB (Phase 8)"]
    EpubSource --> EpubPreview["สร้าง XHTML Quick Preview จาก canonical blocks"]
    EpubPreview --> EpubRevision{"source และ preview revision ยังตรงหรือไม่?"}
    EpubRevision -->|ไม่ตรง / HTML เปลี่ยน| EpubStale["แสดง Stale Warning / บล็อก Package ชั่วคราว"]
    EpubStale --> EpubPreview
    EpubRevision -->|ตรงกัน| EpubPackage["สร้าง nav.xhtml, OPF, CSS และ chapter XHTML<br/>ตรวจ Internal Validator แล้วเผยแพร่ book.epub"]
```

ค่าเริ่มต้นคือ **OneOCR อย่างเดียว (Baseline)**. ตัวเลือก AI จะเปิดหลังการทดสอบการเชื่อมต่อพบ Local LLM เท่านั้น. ในแท็บ HTML ผู้ใช้สามารถสลับแก้ไขได้อย่างอิสระระหว่าง CodeMirror และ Visual Editor แบบ Word โดยระบบรักษาฉบับร่างไว้ไม่ให้สูญหาย และบันทึกผ่านปุ่มหรือคีย์ลัด Ctrl+S/Cmd+S โดยปราศจาก Autosave ที่อาจสร้างความสับสน.

---

### 4. วงจรสถานะงานและการเก็บข้อมูล

```mermaid
stateDiagram-v2
    [*] --> Uploaded: upload ไฟล์สำเร็จ
    Uploaded --> Queued: กดเริ่มงาน (start job)
    Queued --> Cancelled: cancel ก่อนเริ่มงาน
    Queued --> Running: supervisor สั่งเริ่ม worker
    Running --> Completed: ทุกหน้าสำเร็จครบ 100%
    Running --> Partial: OCR หรือ AI สำเร็จบางส่วน
    Running --> Failed: เกิดข้อผิดพลาดร้ายแรง
    Running --> Cancelled: ผู้ใช้สั่งยกเลิก (รวมผลหน้าที่เสร็จ)
    Running --> Failed: restart ระบบแล้วพบงานค้าง (recovery)

    Completed --> Deleted: ผู้ใช้ลบงาน
    Partial --> Deleted: ผู้ใช้ลบงาน
    Failed --> Deleted: ผู้ใช้ลบงาน
    Cancelled --> Queued: เริ่มงานต่อจากหน้าที่เหลือ
    Cancelled --> Deleted: ผู้ใช้ลบงาน
    Completed --> Deleted: cleanup ลบอัตโนมัติตาม retention
    Partial --> Deleted: cleanup ลบอัตโนมัติตาม retention
    Failed --> Deleted: cleanup ลบอัตโนมัติตาม retention
    Cancelled --> Deleted: cleanup ลบอัตโนมัติตาม retention

    state "วงจร HTML Studio" as HtmlExport {
        [*] --> NotGenerated
        NotGenerated --> BasicReady: export basic หรือ AI fallback
        BasicReady --> AIReady: AI semantic tags ผ่าน
        BasicReady --> FinalDraft: แก้ไขใน Code หรือ Visual Editor
        AIReady --> FinalDraft: แก้ไขใน Code หรือ Visual Editor
        FinalDraft --> FinalReady: บันทึกสำเร็จ (Manual Save / Ctrl+S)
        FinalDraft --> Conflict409: Revision ชนกับแท็บอื่น
        Conflict409 --> FinalReady: ยืนยัน Overwrite
        FinalReady --> Stale: ข้อความต้นทาง final.txt ถูกแก้ไขใหม่
        Stale --> BasicReady: สร้าง HTML ใหม่จาก final.txt ล่าสุด
    }

    Completed --> HtmlExport: เข้าแท็บ HTML
    Partial --> HtmlExport: เข้าแท็บ HTML (เฉพาะหน้าที่สำเร็จ)

    state "วงจร EPUB Studio" as EpubExportState {
        [*] --> SelectingSource: เลือก basic / ai / final
        SelectingSource --> GeneratingPreview: กดสร้าง XHTML Quick Preview
        GeneratingPreview --> PreviewReady: XHTML และสารบัญพร้อมแสดงผล
        PreviewReady --> Packaging: กรอก Metadata และกดสร้าง EPUB
        Packaging --> EpubPublished: ผ่าน Internal Validator (book.epub)
        PreviewReady --> EpubStaleWarning: ต้นทาง HTML เปลี่ยนแปลง
        EpubStaleWarning --> GeneratingPreview: สร้าง Quick Preview ใหม่
    }

    HtmlExport --> EpubExportState: เข้าแท็บ EPUB
```

เมื่อยกเลิก ระบบจะรวมข้อความของหน้าที่ OCR สำเร็จแล้วทันที และใส่ `[PAGE N: CANCELLED]` ให้หน้าที่ยังไม่ทำ เพื่อให้ไฟล์ดาวน์โหลดไม่ขาดผลที่มีอยู่. ผู้ใช้กด **เริ่มงานต่อจากหน้าที่เหลือ** ได้โดยไม่ต้อง refresh. หน้า **งาน OCR ก่อนหน้า** แสดงงานล่าสุด เปิดดูหรือดาวน์โหลดงานเดิมได้. การลบรายงานและ cleanup จะไม่ลบงานที่อยู่ในสถานะ `queued` หรือ `running`; Worker ตรวจสถานะก่อนเขียนผลต่อเพื่อไม่ให้ไฟล์ที่ลบแล้วถูกสร้างกลับ.

---

### 5. ขั้นตอนใช้งานบนหน้าเว็บ (End-to-End User Flow)

```mermaid
flowchart TD
    A["เปิด Web Studio: http://127.0.0.1:8000"] --> B["ตรวจสถานะ Local AI (เชื่อมต่อ/Offline)"]
    B --> C["แท็บ 1: อัปโหลดเอกสาร (PDF / PNG / JPG)"]
    C --> D{"ชนิดเอกสารที่อัปโหลด?"}
    D -->|PDF| E["ระบบอ่านและแสดงจำนวนหน้าทั้งหมดทันที"]
    D -->|ภาพ PNG/JPG| E2["ระบบกำหนดเป็น 1 หน้า"]
    E --> F{"ต้องการทำสิ่งใดก่อน?"}
    F -->|ต้องการแยกภาพเท่านั้น| G1["กดปุ่ม 'ดาวน์โหลดภาพแต่ละหน้า (ZIP)'<br/>(ได้ภาพ PNG 200 DPI ทันทีโดยไม่ต้องทำ OCR)"]
    G1 --> A
    F -->|ต้องการแปลงข้อความ| G2["เลือกช่วงหน้าที่เริ่มต้น-สิ้นสุด"]
    E2 --> G2
    G2 --> H{"เลือกโหมดการประมวลผล"}
    H -->|OneOCR อย่างเดียว| I["กด 'เริ่มแปลงหน้า' (OneOCR Baseline)"]
    H -->|OneOCR + Local AI| J["กด 'เริ่มแปลงหน้า' (เปิด Local AI ตรวจแก้)"]
    I --> K["แท็บ 2: ติดตามสถานะ Batch, Progress และ Preview รายหน้า"]
    J --> K
    K --> L{"ยกเลิกงานกลางคันหรือไม่?"}
    L -->|ใช่| M["ระบบรวมผลหน้าที่ทำเสร็จแล้ว (เริ่มต่อหน้าที่เหลือได้)"]
    L -->|ไม่| N["ตรวจทานข้อความใน Text Studio"]
    M --> N
    N --> O["ตรวจทานภาพเทียบข้อความ (คลิกคำเพื่อเลื่อนกรอบ Bounding Box)"]
    O --> P{"ต้องการตรวจแก้คำเพิ่มหรือไม่?"}
    P -->|ใช่| Q["กด 'AI ตรวจคำผิดทั้งหมด' หรือ Accept / Revert ข้อเสนอ"]
    Q --> O
    P -->|ไม่ / แก้ไขพอใจแล้ว| R["กด 'บันทึก' final.txt"]
    R --> S{"ต้องการทำงานต่อในแท็บใด?"}
    S -->|ดาวน์โหลดข้อความ/ภาพ| T1["ดาวน์โหลด raw.txt, corrected.txt, final.txt, ZIP หรือภาพ PDF"]
    S -->|ส่งออก HTML| U["เข้าสู่ แท็บ 3: HTML Studio"]
    S -->|ดูประวัติงาน| V["เข้าสู่ แท็บ 5: งาน OCR ก่อนหน้า (เปิดงานเดิม/ลบงาน)"]
    T1 --> V

    U --> W{"เลือกสร้างโครงสร้าง HTML เริ่มต้น"}
    W -->|Basic HTML| X1["สร้าง basic.html แบบ deterministic"]
    W -->|AI HTML| X2["สร้าง ai.html ด้วย Local AI Semantic Tags"]
    X1 --> Y["พื้นที่ทำงาน HTML Studio: Code / Visual / Preview"]
    X2 --> Y
    Y --> Z{"เลือกรูปแบบการแก้ไข"}
    Z -->|Code View| AA1["แก้ไขซอร์สโค้ด HTML ผ่าน CodeMirror 5.65.21"]
    Z -->|Visual View| AA2["แก้ไขแบบ Word ผ่าน WYSIWYG Editor (Bold/Italic/Heading/Lists)"]
    AA1 <--> AA2
    AA1 --> AB["ดูผลลัพธ์ทันทีใน Sandboxed Preview (CSP)"]
    AA2 --> AB
    AB --> AC["กด 'บันทึก Final HTML' หรือกด Ctrl+S / Cmd+S"]
    AC --> AD{"เกิด Revision Conflict 409 หรือไม่?"}
    AD -->|เกิดการชน| AE["แสดงกล่องข้อความเตือน (เลือกยืนยันเขียนทับหรือยกเลิก)"]
    AE -->|ยกเลิก| Y
    AE -->|ยืนยัน| AF["ระบบ Sanitize (ตัด Head/Title ออกจาก Body) และบันทึก final.html"]
    AD -->|ไม่ชน| AF
    AF --> AG["ดาวน์โหลด final.html หรือไปทำ EPUB ต่อ"]

    AG --> AH["เข้าสู่ แท็บ 4: ส่งออก EPUB (Phase 8)"]
    AH --> AI["เลือกต้นทาง (basic / ai / final) แล้วกด 'สร้าง XHTML Quick Preview'"]
    AI --> AJ["ตรวจสอบเนื้อหาบทและโครงสร้างสารบัญใน Quick Preview"]
    AJ --> AK{"ต้นทาง HTML ถูกแก้ไขใหม่หรือไม่?"}
    AK -->|ถูกแก้ไข| AL["ระบบเตือน Stale Revision (ต้องกดสร้าง Quick Preview ใหม่)"]
    AL --> AI
    AK -->|ถูกต้องและเป็นปัจจุบัน| AM["กรอก Metadata (ชื่อหนังสือ, ผู้แต่ง, ภาษา, เลขเอกสาร)"]
    AM --> AN["กด 'สร้างไฟล์ EPUB' (ระบบรัน Internal Package Validator)"]
    AN --> AO["ดาวน์โหลด book.epub นำไปเปิดอ่านบนโปรแกรมอ่าน e-book"]
    AO --> V
```

---

## การติดตั้งและเริ่มต้นใช้งาน (Getting Started)

### ความต้องการของระบบ (Prerequisites)
- **ระบบปฏิบัติการ:** Windows 10 หรือ Windows 11 (แบบ **64-bit** เท่านั้น เนื่องจาก OneOCR DLL เป็น 64-bit)
- **Python:** Python 3.10 ขึ้นไป (64-bit) พร้อม Python Launcher (`py`)
- **เว็บเบราว์เซอร์:** Google Chrome, Microsoft Edge หรือเบราว์เซอร์ Chromium ทันสมัย

---

### รันด่วน

ชุดนี้มีไฟล์ binary, model, backend และหน้าเว็บครบแล้ว:

1. เปิด **Command Prompt** ในโฟลเดอร์นี้
2. รันสคริปต์ติดตั้งระบบ (จะสร้าง virtual environment และดาวน์โหลด dependencies อัตโนมัติ):
   ```cmd
   .\install.cmd
   ```
3. เริ่มต้นเซิร์ฟเวอร์:
   ```cmd
   .\run_server.cmd
   ```
4. เปิดเบราว์เซอร์ไปที่: **`http://127.0.0.1:8000/`**

---

### ติดตั้ง dependencies ด้วยตนเอง

ใช้เมื่อต้องการสร้าง virtual environment เองแทน `install.cmd`:

1. **ตรวจสอบโฟลเดอร์โมเดล OneOCR:**  
   ตรวจสอบว่ามีไฟล์ binary ครบถ้วนในโฟลเดอร์ `oneOCR/`:
   ```text
   oneOCR/
   ├── oneocr.dll        (DLL เอนจิน OneOCR)
   ├── oneocr.onemodel   (โมเดล ONNX สำหรับภาษาไทย/อังกฤษ)
   └── onnxruntime.dll   (ONNX Runtime 64-bit)
   ```

2. **สร้าง Virtual Environment และเปิดใช้งาน:**
   ```powershell
   py -3 -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

3. **ติดตั้ง Dependencies:**
   ```powershell
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   ```

4. **เตรียมไฟล์การตั้งค่า (`.env`):**
   ```powershell
   Copy-Item .env.example .env
   ```

5. **เริ่มการทำงานของเซิร์ฟเวอร์:**
   ```powershell
   python -m uvicorn src.server:app --host 127.0.0.1 --port 8000 --reload
   ```

---

## การตั้งค่า Local AI ตรวจแก้

ระบบรองรับการเชื่อมต่อกับ **Local LLM / VLM** ผ่าน OpenAI-compatible API (เช่น [LM Studio](https://lmstudio.ai/) หรือ [Ollama](https://ollama.com/)) โดยมีขั้นตอนดังนี้:

1. เปิดโปรแกรม Local LLM และโหลดโมเดลที่ต้องการ (เช่น `google/gemma-3-1b` หรือโมเดลภาษาไทยอื่น ๆ)
2. เริ่มการทำงานของ Local Server ที่ `http://127.0.0.1:1234/v1`
3. เข้าหน้าเว็บตั้งค่าของระบบ: **`http://127.0.0.1:8000/config.html`**
4. กรอกข้อมูลการเชื่อมต่อ:
   - **Base URL:** `http://127.0.0.1:1234/v1` *(จำกัดเฉพาะ localhost/127.0.0.1 เพื่อความปลอดภัย)*
   - **Model:** ระบุชื่อโมเดล เช่น `google/gemma-3-1b`
   - **Timeout:** ค่าเริ่มต้น `60.0` วินาที
5. กดปุ่ม **"ทดสอบการเชื่อมต่อ"** เมื่อขึ้นสถานะพร้อมใช้งาน ให้กด **"บันทึกการตั้งค่า"**
6. ค่าจะถูกบันทึกลง `.env` และมีผลกับงาน OCR+AI รอบถัดไปทันที

---

### ผลทดสอบ Local LLM: ปัญหาสระ `ำ` จาก OCR

ทดสอบเมื่อ 2026-09-29 ผ่าน Local OpenAI-compatible API ที่ `127.0.0.1:1234` โดยวัดว่าผลแก้ไขตรงกับคำที่คาดหวังและสามารถนำไป apply กับข้อความต้นทางได้จริง ชุดทดสอบมี 13 คำ เช่น `ท างาน` → `ทำงาน`, `น ้าท่วม` → `น้ำท่วม`, `ด าน า` → `ดำนำ`, `ข้าวย า` → `ข้าวยำ` และ `เงื่อนง า` → `เงื่อนงำ`.

| วิธี / โมเดล | ผลถูกต้อง | เวลาโดยประมาณ | ข้อสรุป |
|---|---:|---:|---|
| Baseline deterministic rule | **13/13** | ทันที | ใช้เป็นแนวป้องกันหลักสำหรับรูปแบบ “อักษร + เว้นวรรค + า/วรรณยุกต์+า” |
| `google/gemma-4-e2b` | **10/13** | ~108 วินาที | แก้ `ด าน า` ผิดเป็น `ด้านำ`, `ข าขัน` ผิดเป็น `ข้าขัน`, และ `ข้าวย า` ผิดเป็น `ข้าวยา`; ไม่เหมาะเป็นค่าเริ่มต้น |
| `google/gemma-3-1b` | **0/13** | ~64 วินาที | เสนอ `original_text` ไม่ตรงข้อความต้นทางและแก้คำไม่ถูกต้อง จึง apply ผลจริงไม่ได้ |

`gemma-4-e2b` สร้าง `reasoning_content` ก่อนคำตอบ: เมื่อใช้ `max_tokens=600` คำตอบสุดท้ายว่าง เพราะ reasoning ใช้ token หมด; การทดสอบข้างต้นจึงใช้ `max_tokens=1600` และพบ reasoning 685 token. ระบบจึงยังคงใช้กฎ deterministic กับปัญหาสระ `ำ` และให้ Local LLM เสนอการแก้กรณีอื่นเพื่อให้ผู้ใช้ตรวจทานก่อนยอมรับ

#### ตรวจสอบผลของ Prompt กับ `google/gemma-3-1b`

ทดสอบเพิ่มเมื่อ 2026-09-29 ผ่าน API เดิม โดยใช้ `temperature=0` และ `max_tokens=800` เพื่อแยกปัญหา prompt ออกจากการเชื่อมต่อโมเดล ผลพบว่า prompt มีผลต่อรูปแบบคำตอบ แต่โมเดลยังไม่เสถียรกับการประกอบอักขระไทยและ Structured JSON จึงไม่ใช่สาเหตุเดียวของผล 0/13.

| ชุดทดลอง | Prompt ที่ใช้ | ผลตอบกลับ | สรุป |
|---|---|---|---|
| Prompt ระบบปัจจุบัน + 12 คำ | `You are a Thai OCR correction engine. Return only valid JSON ... Do not romanize Thai.` และ `Correct only OCR spelling mistakes ... original_text must be copied exactly from the input.` | ส่ง fenced JSON ที่มี object ราก 2 ตัว; `original_text` ตัดช่องว่างและ `corrected_text` ไม่แก้เป็น `ำ` | JSON ใช้ไม่ได้และไม่ผ่าน validator |
| Prompt ไทยแบบ few-shot + 12 คำ | `ตัวอย่าง: ข้อความ \`ท างาน\` -> {"corrections":[{"original_text":"ท างาน","corrected_text":"ทำงาน"}]}` แล้วสั่งให้แก้รูปแบบอักษร+ช่องว่าง+า โดยคัดลอก `original_text` ตรงตัว | แก้ `ท างาน` → `ทำงาน` ได้ แต่ตอบเพียง 1 รายการจาก 12 | few-shot ช่วยเฉพาะกรณีตัวอย่าง แต่ไม่รองรับงานหลายรายการ |
| คำถามเดี่ยว | `ข้อความ OCR คือ \`ผู้อ านวยการ\` คำที่ถูกต้องคืออะไร? ตอบเฉพาะคำไทยหนึ่งคำ ห้ามอธิบาย ห้ามใช้อักษรอังกฤษ` | `ผู้อานวยการ` | ยังลบช่องว่างแต่ไม่สร้าง `ำ` |
| คำถามสั้น | `รวม \`ท างาน\` ให้เป็นคำไทยที่ถูกต้อง แล้วตอบเฉพาะผลลัพธ์` | ตอบเป็นรายการคำหลายคำ เช่น `การทำงาน`, `การทำหน้าที่` | ไม่ทำตามรูปแบบผลลัพธ์และมีการแต่งเติม |

ข้อความ prompt เต็มของชุด few-shot ที่ให้ผลดีที่สุดในการทดสอบนี้:

```text
ตอบ JSON เท่านั้น ห้ามอธิบาย ห้ามแปลไทยเป็นอักษรโรมัน

ตัวอย่าง: ข้อความ `ท างาน` -> {"corrections":[{"original_text":"ท างาน","corrected_text":"ทำงาน"}]}

จงแก้เฉพาะช่องว่างที่ทำให้สระ ำ กลายเป็น อักษร+ช่องว่าง+า ในรายการนี้ โดยคัดลอก original_text ตรงตัว:
ท างาน
ผู้อ านวยการ
ส ารวจ
ก าลัง
น ้าท่วม
น าเกลือ
ด าน า
ข าขัน
ค าพูด
ข้าวย า
ล าน ้า
เงื่อนง า
```

ข้อความ prompt อื่นที่ใช้ในการทดสอบ (รายการ 12 คำใช้ชุดเดียวกับด้านบน):

```text
[system]
You are a Thai OCR correction engine. Return only valid JSON:
{"corrections":[{"original_text":"exact substring","corrected_text":"corrected Thai","category":"spelling","reason":"short"}]}
Do not romanize Thai.

[user]
Correct only OCR spelling mistakes in this text. original_text must be copied exactly from the input.
<รายการ 12 คำด้านบน>

[single question]
ข้อความ OCR คือ `ผู้อ านวยการ`
คำที่ถูกต้องคืออะไร? ตอบเฉพาะคำไทยหนึ่งคำ ห้ามอธิบาย ห้ามใช้อักษรอังกฤษ

[short question]
รวม `ท างาน` ให้เป็นคำไทยที่ถูกต้อง แล้วตอบเฉพาะผลลัพธ์
```

ดังนั้นระบบใช้กฎ deterministic ที่ตรวจสอบได้สำหรับรูปแบบนี้ต่อไป; Local LLM ใช้เสนอการแก้กรณีอื่นเท่านั้น และทุกผลต้องผ่าน validator ก่อนนำไปใช้

---

## สัญญาข้อมูลและไฟล์ผลลัพธ์ (Data Contract)

ไฟล์ต้นฉบับและผลลัพธ์ของแต่ละงานจะถูกจัดเก็บแยกตามโฟลเดอร์ใน `files/{job_id}/`:

| ชื่อไฟล์ | คำอธิบายและเนื้อหา |
|---|---|
| **`raw.txt`** | ข้อความดิบที่ประกอบตามลำดับอ่านที่ได้จาก PDF Text หรือ OneOCR ก่อนผ่าน AI |
| **`corrected.txt`** | ข้อความหลังผ่าน Local AI ตรวจแก้ตามโครงสร้าง JSON (มีเฉพาะเมื่อเปิดโหมด AI) |
| **`final.txt`** | ข้อความฉบับทำงานล่าสุดที่ผู้ใช้แก้ไข หรือยอมรับข้อเสนอผ่านหน้าเว็บ |
| **`ocr.json`** | ข้อมูลเชิงลึกของทุกหน้า: บล็อกข้อความ, พิกัด Bounding Box 4 จุด, เส้นทางที่ใช้ (Routing) และสถานะ |
| **`changes.json`** | รายการข้อเสนอการแก้ไขของ AI: ข้อความเดิม, ข้อความใหม่, ตำแหน่งออฟเซ็ต และสถานะ (`pending`, `accepted`, `reverted`) |
| **`page-images.zip`** | สร้างเมื่อขอดาวน์โหลดภาพ PDF; ภายในมี PNG หนึ่งไฟล์ต่อหนึ่งหน้าตามช่วงงาน เช่น `page_0001.png` ที่ 200 DPI |
| **`export/epub/preview.xhtml`** | XHTML Quick Preview ที่สร้างก่อน package ใช้ sandbox และ CSP |
| **`export/epub/preview_payload.json`** | canonical payload ของบท, metadata, source revision และ preview revision ที่ใช้สร้าง EPUB |
| **`export/epub/book.epub`** | EPUB แบบ reflowable ที่ผ่าน structural validator ภายในระบบ |
| **`export/epub/epub_meta.json`** | สถานะ Phase 8, source/preview revision, hash, validation result และขนาดไฟล์ |

---

## รายละเอียด REST API (API Reference)

ระบบขับเคลื่อนด้วย **FastAPI** รันบน `http://127.0.0.1:8000` (จำกัดเฉพาะ Loopback เพื่อความเป็นส่วนตัว) มีระบบเอกสาร API แบบ Interactive ให้อัตโนมัติ:

- **Swagger UI**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)
- **OpenAPI Schema**: [http://127.0.0.1:8000/openapi.json](http://127.0.0.1:8000/openapi.json)

### 1. หมวดตรวจสุขภาพและสถานะระบบ (Health & Diagnostics)

| Method | Endpoint | คำอธิบาย |
|---|---|---|
| `GET` | `/api/health` | ตรวจสอบสถานะเซิร์ฟเวอร์ ข้อมูลคิวงาน (`queue_info`) และการเชื่อมต่อฐานข้อมูล |

### 2. หมวดตั้งค่า Local AI (Local LLM Configuration)

| Method | Endpoint | พารามิเตอร์ / Body | คำอธิบาย |
|---|---|---|---|
| `GET` | `/api/ai/status` | - | ตรวจสอบว่า Local LLM พร้อมใช้งานหรือไม่ (`healthy` / `offline`) |
| `GET` | `/api/ai/config` | - | ดึงค่าคอนฟิกปัจจุบัน (`base_url`, `model`, `timeout`) โดยซ่อน API Key |
| `POST` | `/api/ai/config/test` | JSON: `{ base_url, model, timeout, api_key? }` | ทดสอบเชื่อมต่อไปยัง endpoint โดยยังไม่บันทึก |
| `PUT` | `/api/ai/config` | JSON: `{ base_url, model, timeout, api_key? }` | บันทึกการตั้งค่าลง `.env` และมีผลกับงานถัดไปทันที |

### 3. หมวดจัดการวงจรงาน OCR (Job Lifecycle)

| Method | Endpoint | พารามิเตอร์ / Body | คำอธิบาย |
|---|---|---|---|
| `POST` | `/api/upload` | Multipart/form-data:<br>• `file`: ไฟล์ PDF / รูปภาพ<br>• `max_pages_limit`: (optional)<br>• `max_size_limit`: (optional) | อัปโหลดและตรวจสอบไฟล์ ตรวจสอบความปลอดภัย สร้าง `job_id` |
| `POST` | `/api/jobs/{job_id}/start` | JSON: `{ enable_ai: true, page_start?: 1, page_end?: N, include_page_numbers?: true }` | นำงานเข้าคิวประมวลผล OneOCR / Local AI |
| `GET` | `/api/jobs/{job_id}/status` | Path: `job_id` | เช็คสถานะงานโดยละเอียดระดับหน้าและ latency |
| `POST` | `/api/jobs/{job_id}/cancel` | Path: `job_id` | ยกเลิกงานที่กำลังรันหรือรอคิว พร้อมหยุด Worker ทันที |
| `POST` | `/api/jobs/{job_id}/retry` | JSON: `{ retry_mode: "failed_only" \| "ai_only" \| "full" \| "full_text_ai" }` | ประมวลผลซ้ำเฉพาะหน้าที่ล้มเหลว หรือรันซ้ำเฉพาะ AI |
| `GET` | `/api/jobs` | Query: `limit=50` | ดึงรายการประวัติงานทั้งหมดในฐานข้อมูล SQLite |
| `POST` | `/api/jobs/{job_id}/review` | Query: `new_status=unreviewed \| in_review \| reviewed` | อัปเดตสถานะการตรวจทานของงาน |

### 4. หมวดดูเนื้อหาและตรวจแก้รายหน้า (Page Data & Human-in-the-Loop)

| Method | Endpoint | พารามิเตอร์ / Body | คำอธิบาย |
|---|---|---|---|
| `GET` | `/api/jobs/{job_id}/pages/{page_id}/image` | Path: `job_id`, `page_id` | ดึงรูปภาพเรนเดอร์ของหน้านั้นสำหรับแสดงใน Dual-pane Viewer |
| `GET` | `/api/jobs/{job_id}/pages/{page_id}/data` | Path: `job_id`, `page_id` | ข้อมูลเต็มของหน้า: `raw_text`, `corrected_text`, `final_text`, Bounding boxes, AI proposals |
| `PUT` | `/api/jobs/{job_id}/pages/{page_id}/edit` | JSON: `{ source_revision: int, edited_text: string, check_conflict: bool }` | บันทึกข้อความที่ผู้ใช้แก้ไขเอง ป้องกันการเขียนทับชนกัน (HTTP 409) |
| `POST` | `/api/jobs/{job_id}/pages/{page_id}/corrections/{change_id}/accept` | Path: `change_id` | ยอมรับข้อเสนอแก้คำผิดจุดนั้นของ AI |
| `POST` | `/api/jobs/{job_id}/pages/{page_id}/corrections/{change_id}/revert` | Path: `change_id` | ปฏิเสธข้อเสนอ AI และย้อนกลับไปใช้ข้อความเดิมจาก OCR |
| `POST` | `/api/jobs/{job_id}/pages/{page_id}/corrections/accept-all` | Query: `source_revision?` | ยอมรับข้อเสนอของ AI ทุกจุดในหน้านั้นพร้อมกัน |
| `POST` | `/api/jobs/{job_id}/pages/{page_id}/corrections/revert-all` | Query: `source_revision?` | ปฏิเสธและย้อนคืนข้อความเดิมจาก OCR ทุกจุดในหน้านั้น |

### 5. หมวดดาวน์โหลดผลลัพธ์ (Download & Artifacts)

| Method | Endpoint | ไฟล์ที่รองรับ | คำอธิบาย |
|---|---|---|---|
| `GET` | `/api/jobs/{job_id}/download/{file_type}` | `raw.txt`<br>`corrected.txt`<br>`final.txt`<br>`ocr.json`<br>`changes.json`<br>`bundle.zip`<br>`page-images.zip` | ดาวน์โหลดไฟล์ผลลัพธ์ตามประเภทที่ต้องการ (กรณีงานสถานะ `partial` หรือ `failed` จะมี `X-Job-Warning` แจ้งเตือนใน Header) |

### 6. หมวดส่งออกโครงสร้าง HTML (Structured HTML Export)

| Method | Endpoint | พารามิเตอร์ / Body | คำอธิบาย |
|---|---|---|---|
| `POST` | `/api/jobs/{job_id}/export/html` | JSON: `{ mode: "basic" \| "ai" }` | สร้างเอกสาร HTML โครงสร้าง (`basic` = deterministic, `ai` = ใช้ AI จัดโครงสร้างหัวข้อ/ย่อหน้า) |
| `GET` | `/api/jobs/{job_id}/export/html/status` | Path: `job_id` | ตรวจสอบสถานะการแปลง HTML และ revision ว่าล้าสมัย (stale) หรือไม่ |
| `GET` | `/api/jobs/{job_id}/export/html/{variant}` | Path: `variant` = `basic` \| `ai` \| `final` | ดาวน์โหลดไฟล์ HTML โครงสร้าง (RFC 5987 UTF-8 attachment) |
| `GET` | `/api/jobs/{job_id}/export/html/{variant}/preview` | Path: `variant` = `basic` \| `ai` \| `final` | ดูตัวอย่าง HTML แบบ Sandboxed CSP ปลอดภัย |
| `PUT` | `/api/jobs/{job_id}/export/html/final` | JSON: `{ html_content, base_revision?, overwrite: bool }` | บันทึกการแก้ไขโค้ด HTML ฉบับสุดท้ายด้วยตนเอง (HTTP 409 หากชน) |

HTML export ใช้ฟอนต์ระบบในเครื่องและไม่โหลด Google Fonts หรือทรัพยากรภายนอก. โหมด `basic` เป็น deterministic; โหมด `ai` ใช้ได้เมื่อ Local LLM พร้อมและถูกจำกัดให้ทำงานพร้อมกับ OCR+AI ได้ครั้งละหนึ่งงาน. การวัดเวลา/VRAM ของ AI และ precision/recall ของ semantic tags จะรายงานต่อเมื่อมีผลวัด Local LLM จริงและเฉลยระดับ element ที่ผู้ตรวจรับรองแล้วเท่านั้น.

### 7. หมวดส่งออก EPUB และ XHTML Quick Preview

| Method | Endpoint | พารามิเตอร์ / Body | คำอธิบาย |
|---|---|---|---|
| `POST` | `/api/jobs/{job_id}/export/epub/preview` | JSON: `{ source_variant, chapter_split, metadata }` | สร้าง XHTML Quick Preview โดยยังไม่ package EPUB |
| `GET` | `/api/jobs/{job_id}/export/epub/preview` | Path: `job_id` | แสดง XHTML Quick Preview พร้อม CSP sandbox และ nosniff |
| `POST` | `/api/jobs/{job_id}/export/epub` | JSON: `{ base_preview_revision }` | ตรวจ revision แล้ว package EPUB; คืน 409 เมื่อต้นทางหรือ Preview เปลี่ยน |
| `GET` | `/api/jobs/{job_id}/export/epub/status` | Path: `job_id` | ตรวจ `preview_ready`, `ready`, `stale`, validation และ file metadata |
| `GET` | `/api/jobs/{job_id}/export/epub/download` | Path: `job_id` | ดาวน์โหลด `.epub` แบบ attachment ชื่อ UTF-8 |

Quick Preview ใช้ XHTML ชุดข้อมูลเดียวกับ chapter XHTML ใน EPUB และไม่ใช้ EPUB renderer. Phase 8 ไม่เรียก Local LLM เพิ่มเอง; ถ้าต้องการ semantic structure จาก AI ให้เลือก `ai.html` ที่ผ่าน Phase 7 validator แล้ว.

### 8. หมวดบริหารจัดการและล้างข้อมูล (Admin & Retention Cleanup)

| Method | Endpoint | พารามิเตอร์ / Body | คำอธิบาย |
|---|---|---|---|
| `POST` | `/api/admin/cleanup` | Query: `max_age_seconds?` | สั่งลบงานที่หมดอายุตามนโยบาย Retention โดยไม่แตะต้องงานที่กำลังรัน |
| `DELETE` | `/api/jobs/{job_id}` | Path: `job_id`, Query: `force: bool` | ลบงานและโฟลเดอร์ผลลัพธ์ของ `job_id` นั้นทิ้งอย่างถาวร |

### ตัวอย่างการเรียกใช้งานด้วย cURL (Quick Example)

```bash
# 1. อัปโหลดเอกสาร
curl -F "file=@document.pdf" http://127.0.0.1:8000/api/upload
# ตอบกลับ: {"job_id":"abc123xyz","status":"queued","total_pages":5,...}

# 2. สั่งเริ่มประมวลผล (หน้า 1-5, เปิด AI)
curl -X POST http://127.0.0.1:8000/api/jobs/abc123xyz/start \
  -H "Content-Type: application/json" \
  -d '{"enable_ai": true, "page_start": 1, "page_end": 5}'

# 3. ตรวจสอบสถานะความคืบหน้า
curl http://127.0.0.1:8000/api/jobs/abc123xyz/status

# 4. ดาวน์โหลดผลลัพธ์ฉบับสมบูรณ์
curl -O http://127.0.0.1:8000/api/jobs/abc123xyz/download/final.txt
```

---

## โครงสร้างโฟลเดอร์ (Repository Structure)

```text
publish/
├── src/                    # ซอร์สโค้ดหลักของ Backend และ OCR Pipeline
│   ├── server.py           # FastAPI Web Application & REST Endpoints
│   ├── pipeline.py         # OCR & Assembly Processing Pipeline
│   ├── worker_process.py   # OCR Subprocess Worker (โหลด oneocr.dll แยก)
│   ├── job_manager.py      # Job Supervisor & Process Queue Manager
│   ├── database.py         # SQLite WAL Database Handler
│   ├── oneocr_wrapper.py   # OneOCR ctypes Wrapper & ABI Definitions
│   ├── diff_engine.py      # Character-level Diff & Proposal Engine
│   ├── llm_client.py       # Local LLM OpenAI-compatible Client
│   ├── html_exporter.py    # Structured HTML Export & Strict Allowlist Sanitizer
│   ├── epub_exporter.py    # XHTML Quick Preview, EPUB 3 Packaging & Validator
│   └── cleanup_service.py  # ลบงานตามคำสั่งจากหน้า History / API
├── static/                 # หน้าเว็บและส่วนติดต่อผู้ใช้ (Frontend แยก 5 แท็บ)
│   ├── index.html          # โครงหลัก Web Studio และ Template Partials Container
│   ├── text.html           # แท็บผลข้อความ Dual-Pane Studio
│   ├── html.html           # แท็บ HTML Studio (CodeMirror + Visual Editor + Preview)
│   ├── epub.html           # แท็บ EPUB Studio (XHTML Quick Preview + Packager)
│   ├── config.html         # หน้าจอตั้งค่า Local LLM
│   ├── app.js              # ตัวจัดการสถานะกลางและประสานงานแท็บ (App Controller)
│   ├── text.js             # ตัวควบคุมแท็บผลข้อความ (Text Controller)
│   ├── html.js             # ตัวควบคุมแท็บ HTML และ CodeMirror (HTML Controller)
│   ├── epub.js             # ตัวควบคุมแท็บ EPUB และ Quick Preview (EPUB Controller)
│   ├── visual.js           # ตัวควบคุม Visual Editor แบบ Word (WYSIWYG Controller)
│   ├── vendor/codemirror/  # ไลบรารี CodeMirror 5.65.21 สำหรับใช้งานแบบ Offline
│   └── app.css             # ดีไซน์และชุดแต่ง Modern Dark/Light Theme
├── oneOCR/                 # OneOCR Binary DLL & Model Runtime (64-bit)
├── data/                   # SQLite job database (สร้างขณะใช้งาน)
├── files/                  # ไฟล์อัปโหลดและผลลัพธ์ (สร้างขณะใช้งาน)
├── checklist.md            # จุดตรวจบังคับและเกณฑ์การตรวจรับราย Phase
├── manual.md               # คู่มือการติดตั้ง เริ่ม/หยุดระบบ และการบำรุงรักษา
├── gemini.md               # บันทึกผลการตรวจรับและสถาปัตยกรรมระบบ (Read-only)
├── install.cmd             # สร้าง virtual environment และติดตั้ง dependencies
├── run_server.cmd          # เริ่ม FastAPI server
├── stop_server.cmd         # หยุด FastAPI server ที่ port 8000
├── requirements.txt        # Python dependencies
└── readme.md               # เอกสารภาพรวมและขอบเขตของโครงการ (หน้านี้)
```

---

## ผลการทดสอบและเกณฑ์ตรวจรับ (Verification & Benchmarks)

สถานะด้านล่างสรุปจากหลักฐานที่บันทึกในโครงการ ณ วันที่ 2026-10-03 เพื่อไม่ให้ผลที่ยังไม่มีหลักฐานถูกแสดงเป็นผ่าน

### ผ่านตามขอบเขตที่ทดสอบ

| รายการทดสอบ | เกณฑ์ที่กำหนด | ผลการทดสอบจริง | สถานะ |
|---|---|---|:---:|
| **การตรวจรับ UI, Visual Editor และ EPUB (Section 0.9)** | ผ่านข้อกำหนด 12 ข้อ | **46/46 PASS (7.79s)**, Acceptance **6/6 PASS** | **PASSED** |
| **CER เอกสารไทยตัวพิมพ์ชัด** | $\le 5.0\%$ | **0.04%** | **PASSED** |
| **CER รวมทุกกลุ่มเอกสาร (Routing จริง)** | $\le 10.0\%$ | **0.83%** | **PASSED** |
| **ความถูกต้องของช่องข้อมูลสำคัญ (Key Fields)** | $\ge 95.0\%$ (Exact Match) | **100.00% (146/146 ช่อง)** | **PASSED** |
| **Diff Engine & Revert Fidelity** | Diff 100%, Revert 100% | ตรงกับ raw text byte-for-byte 100% | **PASSED** |
| **ความเสถียรสะสม $\ge 200$ หน้าต่อเนื่อง** | ไม่มี Crash, ไม่ OOM | 200/200 หน้าสำเร็จ (Peak RAM **33.28 MB**) | **PASSED** |
| **การทำงานแบบออฟไลน์ (Network Isolation)** | 0 คำขอนอก Loopback | บล็อกทุก external network request 100% | **PASSED** |
| **Browser Automation (Chrome & Edge)** | ทำงานสมบูรณ์ผ่านเว็บ | ผ่าน 100% ทั้ง Google Chrome และ Edge | **PASSED** |
| **Backend, queue และ recovery** | สถานะงานและการกู้คืนถูกต้อง | ผ่าน 21/21 tests | **PASSED** |
| **หน้าเว็บเลือกช่วงและ batch OCR** | เลือกช่วง, แบ่ง batch ละ 200 หน้า และตรวจ scope | ผ่าน 5/5 tests | **PASSED** |

### ไม่ผ่าน

| รายการทดสอบ | ผล | สาเหตุ |
|---|:---:|---|
| Local LLM `google/gemma-3-1b` สำหรับชุดทดสอบสระ `ำ` 13 คำ | **FAILED (0/13)** | ผลแก้ไม่ตรงต้นฉบับหรือคำที่คาดหวัง จึงไม่ผ่าน validator และไม่ใช้เป็น baseline |
| Local LLM `google/gemma-4-e2b` สำหรับชุดทดสอบสระ `ำ` 13 คำ | **PARTIAL (10/13)** | มีคำแก้ผิด 3 คำและใช้เวลานาน จึงไม่ใช้เป็น default |

### ยังไม่ได้ทดสอบ / รอหลักฐาน / ยกเว้นชั่วคราว

| รายการ | สถานะ | เหตุผลหรือขอบเขตที่เหลือ |
|---|:---:|---|
| ชุดเอกสารขยาย 2,185 หน้า | **NOT TESTED** | ต้องประมวลผลครบ ตรวจ disk mapping และจัดทำ ground truth ก่อนรับรอง Phase 2–3 ครอบคลุมไฟล์ขยาย |
| Benchmark AI สำหรับเอกสารขยาย | **NOT TESTED** | รอ Phase 2 และ ground truth ที่ล็อกแล้ว |
| งานจริง 100 หน้า: เวลา/RAM/VRAM | **NOT TESTED** | ไม่มีเอกสารทดสอบที่ตรงเงื่อนไขเดิม; ผลเสถียรภาพ 200 หน้าไม่ทดแทนเกณฑ์นี้ |
| Accept/Revert จากข้อเสนอ AI จริง 10 จุด | **NOT TESTED** | ยังไม่มีเอกสารจริงที่สร้างข้อเสนอได้ครบ 10 จุด |
| ภาพหมุน 90° / 180° / 270° | **NOT TESTED** | ไม่มีตัวอย่างเอกสารจริงสำหรับตรวจรับ |
| PDF เสีย, PDF ติดรหัสผ่าน และภาพใหญ่ | **EXEMPTED** | ยกเว้นโดยเจ้าของงาน; ระบบยังคงตอบ error HTTP 400/422/413 |
| ติดตั้งบน clean target machine จากศูนย์ | **NOT TESTED** | รอทดสอบบนเครื่องปลายทางจริงหรือจัดเตรียม wheelhouse แบบ offline |
| HTML Export AI latency / VRAM | **NOT TESTED** | ยังไม่มีผลวัดซ้ำได้จาก Local LLM และตัววัด VRAM; ไม่ใช้ค่าประมาณแทนผลจริง |
| HTML Export precision / recall | **NOT TESTED** | manifest ปัจจุบันมีเพียงยอดรวม ต้องมีเฉลยระดับ element ที่ผู้ตรวจรับรองก่อนคำนวณ |
| Browser automation Phase 7 หลังปรับ offline/XSS/download/409 | **PENDING** | โค้ดและ syntax ตรวจแล้ว; รอรัน integration suite ใน workspace แยกเพื่อเก็บหลักฐานใหม่ |
| Phase 8 EPUB Export & XHTML Quick Preview | **IN PROGRESS** | Core/API tests 6/6 PASS และ smoke test 44 หน้าผ่าน internal validator; รอ EPUBCheck, Chrome/Edge automation, reader compatibility และ benchmark |
| การยอมรับข้อจำกัดก่อนใช้งานจริง | **PENDING** | รอเจ้าของงานตรวจผลและยอมรับข้อจำกัดที่ระบุไว้ |

## ข้อควรรู้ก่อนเผยแพร่บน GitHub

- ห้าม commit `.env`, `venv/`, `data/jobs.db` และไฟล์ใน `files/` เพราะอาจมีค่า Local LLM หรือเอกสารที่ผู้ใช้อัปโหลด
- repository มี `.gitignore` สำหรับตัดไฟล์ runtime เหล่านี้ออกแล้ว
- ตรวจสิทธิ์การแจกจ่าย OneOCR binary และ model ตามนโยบายองค์กรหรือสิทธิ์ของ Windows ก่อนเผยแพร่ repository แบบสาธารณะ
- การตรวจแก้ด้วย AI เป็นทางเลือก; ผู้ใช้ใหม่ยังใช้งาน OCR แบบ Baseline ได้โดยไม่ต้องติดตั้งหรือเปิด Local LLM

---

## สิทธิ์การใช้งานและข้อจำกัดความรับผิดชอบ (License & Disclaimer)

- ซอร์สโค้ดและระบบเว็บนี้พัฒนาขึ้นเพื่อการใช้งานภายในเครื่อง (Localhost Desktop Utility)
- ไบนารีและโมเดล OneOCR (`oneocr.dll`, `oneocr.onemodel`, `onnxruntime.dll`) มาจาก Windows 11 Snipping Tool สำหรับการใช้งานส่วนบุคคลบนระบบปฏิบัติการ Windows ที่มีลิขสิทธิ์ถูกต้อง
