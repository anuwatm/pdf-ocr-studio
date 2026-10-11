# AI CLI translation trial — 2026-10-09

## เป้าหมาย

ทดลองแปล OCR จาก `demo/12.png` เป็นไทยแบบวิชาการผ่าน AI CLI แล้วเปรียบเทียบกับ Local Translation provider เดิม

## ผลตรวจ

- มี CLI: Gemini CLI, Codex CLI และ Aider
- Codex CLI แบบ `--oss --local-provider lmstudio` ไม่เลือก `google/gemma-4-e2b` ที่มีอยู่ และเริ่มดาวน์โหลด `openai/gpt-oss-20b` ขนาด 12.11 GB จึงหยุดทันทีที่ประมาณ 1.5%; ยังไม่มีผลแปล
- ไม่ลบ partial download เพราะนโยบายโครงการบังคับให้ขออนุญาตก่อนลบไฟล์
- Gemini CLI local routing ยังไม่พร้อม: ไม่มี LiteRT-LM binary/model/settings และต้องรัน setup/download เพิ่ม
- Gemini CLI cloud พร้อมเรียกแบบ headless แต่ต้องได้รับ consent ที่ระบุชัดว่าจะส่ง OCR ทั้งหมดจาก `demo/12.png` ไป Google Cloud

## มติ adapter หลัก

- กำหนด `Codex CLI` และ `Gemini CLI` เป็น AI CLI หลักของ Phase 10
- LM Studio CLI เป็น adapter รองสำหรับ compatibility/local fallback
- ส่ง request แบบ UTF-8 JSON/NDJSON ทาง stdin; รับ structured JSON ทาง stdout และแยก stderr เป็น diagnostic
- Codex ใช้ `codex exec` แบบ ephemeral/read-only พร้อม trusted output schema
- Gemini ใช้ headless + JSON + plan/sandbox; ห้าม yolo/auto-edit/raw output
- Cloud mode ต้องขอ consent และระบุปลายทาง; local mode ต้องตรวจ model ก่อนและห้าม auto-download

## AI Command Interface

- ChatGPT CLI ใช้คำสั่ง `codex`
- Gemini CLI เลือกคำสั่ง `gemini` หรือ `agy` ได้
- `agy` รุ่นที่ตรวจพบคือ `1.3.2`; รองรับ stdin, JSON/stream-json, JSON schema, plan mode และ sandbox
- บันทึกตัวเลือกด้วย `LLM_CLI_PROVIDER`; LM Studio `lms` คงเป็น adapter รอง

## Claude CLI

- ใช้คำสั่ง `claude` (Claude Code CLI); เครื่องปัจจุบันยังไม่ติดตั้ง
- Automation ใช้ stdin + `-p --input-format text --output-format json --permission-mode plan --max-turns 1`
- Block Bash/Edit/Write/NotebookEdit/WebFetch/WebSearch และใช้ isolated working directory
- Cloud destination คือ Anthropic ต้องผ่าน consent ก่อนส่งข้อความเอกสาร
- เอกสารอ้างอิง: https://docs.anthropic.com/en/docs/claude-code/cli-usage

## ข้อเสนอ

ใช้ AI CLI เป็น provider เสริมสำหรับทดลอง/benchmark ไม่ควรแทน provider API หลักทันที เพราะ CLI มี auth, model download, output format, timeout และ version behavior ที่เปลี่ยนได้ ควรบังคับ stdin-only, no tools/plan mode, JSON segment IDs, timeout/cancel, cloud consent และ post-validator เดิม

Prompt ที่เตรียมไว้: `prompt_th_academic_full.txt` ขนาด 4,633 bytes
