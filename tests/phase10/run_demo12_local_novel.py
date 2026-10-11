import json
import os
import threading
import time
from pathlib import Path

from src.pipeline import ProcessingPipeline
from src.structured_layout import generate_structured_exports
from src.translation_tasks import TranslationTasks

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/"demo"/"12.png"
RUN_ROOT=ROOT/"phase10"/"demo12_local_novel_th"
FILES=RUN_ROOT/"files"
JOB="demo12"
JOB_DIR=FILES/JOB


class ExistingJobDB:
    def get_job_status(self,job_id): return object() if job_id==JOB else None


class LocalManager:
    def __init__(self): self.ai_lock=threading.Lock()


def main():
    resume=os.getenv("TRANSLATION_RESUME","").strip().lower() in {"1","true","yes"}
    JOB_DIR.mkdir(parents=True,exist_ok=True)
    timings={};started=time.perf_counter()
    if resume and (JOB_DIR/"ocr.json").exists():
        ocr=json.loads((JOB_DIR/"ocr.json").read_text(encoding="utf-8"))
        timings["ocr_seconds"]=0.0
        timings["structured_seconds"]=0.0
    else:
        pipeline=ProcessingPipeline(dll_dir=str(ROOT/"oneOCR"))
        try:
            ocr=pipeline.process_file(str(SOURCE),job_id=JOB,output_dir=str(JOB_DIR))
        finally: pipeline.close()
        timings["ocr_seconds"]=time.perf_counter()-started
        generate_structured_exports(JOB,files_dir=str(FILES))
        timings["structured_seconds"]=time.perf_counter()-started-timings["ocr_seconds"]

    tasks=TranslationTasks(ExistingJobDB(),LocalManager(),str(FILES))
    config={"source_variant":"structured","source_language":"en","target_language":"th",
            "style":"novel","provider":"local","cloud_consent":False,
            "manual_strategy":"reset","preserve_manual_final":False,"translate_toc":True}
    progress=tasks.start(JOB,config,resume=resume)
    deadline=time.time()+600
    while progress.get("status") in {"queued","running","cancelling"} and time.time()<deadline:
        time.sleep(.5);progress=tasks.status(JOB)
    if progress.get("status") in {"queued","running","cancelling"}:
        tasks.cancel(JOB);raise TimeoutError("Translation did not finish within 600 seconds")
    model=tasks.result(JOB);timings["total_seconds"]=time.perf_counter()-started
    report={"date":"2026-10-09","input":"demo/12.png","input_bytes":SOURCE.stat().st_size,
        "ocr_status":ocr.get("status"),"ocr_characters":len(ocr.get("raw_text", "")),
        "ocr_pages":len(ocr.get("pages",[])),"translation_config":config,"resume":resume,
        "translation_status":progress.get("status"),"translation_error":progress.get("error"),
        "detected_language":model.get("detected_language"),"language_confidence":model.get("language_confidence"),
        "segments":len(model.get("segments",[])),"warnings":model.get("warnings",[]),"timings":timings,
        "artifacts":{"ocr":str(JOB_DIR/"ocr.json"),"source_text":str(JOB_DIR/"raw.txt"),
            "translation":str(JOB_DIR/"export"/"translation"/"translation.json"),
            "translated_text":str(JOB_DIR/"export"/"translation"/"translated.txt"),
            "translated_html":str(JOB_DIR/"export"/"translation"/"translated.html")}}
    (RUN_ROOT/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if progress.get("status")!="completed": raise RuntimeError(progress.get("error") or f"Translation ended as {progress.get('status')}")


if __name__=="__main__":main()
