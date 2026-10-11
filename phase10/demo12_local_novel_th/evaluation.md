# demo/12.png — Local AI → ไทย style นิยาย

วันที่ทดสอบ: 2026-10-09

## ผลระบบ

- OCR OneOCR: completed, 1 หน้า, 3,350 ตัวอักษร
- Provider/model: Local AI / `google/gemma-4-e2b`
- ภาษา: `en` → `th`; style `novel`
- Translation: completed, 41/41 segments, warning 0
- Artifacts: `raw.txt`, `translation.json`, `translated.txt`, `translated.html`

## สิ่งที่แก้ระหว่างทดสอบ

- จำกัด Local/Hybrid batch ค่าเริ่มต้น 4 segments และรองรับ `LOCAL_TRANSLATION_BATCH_SEGMENTS=1..8`
- เพิ่ม per-segment target-language validator; ข้อความอังกฤษที่ถูก copy ต้องเป็น `partial` แทน false `completed`
- resume เฉพาะ segment ที่ยังไม่ผ่าน โดยเก็บผลเดิม
- ให้ Local AI เห็นตัวเลข/สูตรจริง แล้วตรวจ critical token หลังแปล
- แก้ false positive ของเลขที่ตามด้วย comma และ `i.e.`
- แก้ code detector ที่เคยตีความ prose ซึ่งมีคำว่า `function` เป็น code

## ประเมินคุณภาพด้วยคน

ผล: **ยังไม่ผ่าน quality acceptance**

คำแปลครบทุก segment และรักษาตัวเลข/สูตรสำคัญ แต่ Structured OCR แยกข้อความตามบรรทัด ทำให้คำและประโยคต่อเนื่องถูกตัด เช่น `hyperparameter / tuning`, `lay- / ers` และ `ground / truth` จึงเกิดสำนวนขาดตอนหรือแปลคำครึ่งเดียว นอกจากนี้ style `novel` ไม่เหมาะกับหนังสือ IT และไม่ตรงเกณฑ์ `12.png` ใน checklist ที่กำหนด style `academic`

ผลนี้ใช้ยืนยัน local pipeline, resume, validator และ Text/HTML export เท่านั้น ยังใช้ปิด quality gate ของ `12.png` ไม่ได้
