import json
import statistics
import time
import tracemalloc
from pathlib import Path

from src.translation_core import create_model, export_results

ROOT=Path(__file__).resolve().parents[2]
FILES=ROOT/"tests"/"artifacts"
JOB="phase10_core_job"
CONFIG={"source_variant":"final","source_language":"en","target_language":"th","style":"academic","provider":"local"}


def main():
    durations=[];tracemalloc.start()
    for _ in range(10):
        started=time.perf_counter();model=create_model(str(FILES),JOB,CONFIG)
        for segment in model["segments"]:
            if segment["status"]=="pending":
                segment.update(translated_text=segment["source_text"],final_text=segment["source_text"],status="translated")
        export_results(str(FILES),JOB,model);durations.append(time.perf_counter()-started)
    _,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
    ordered=sorted(durations);report={"scope":"deterministic translation model/validator/Text-HTML export; provider latency excluded",
        "runs":10,"median_seconds":statistics.median(durations),"p95_seconds":ordered[9],"peak_tracemalloc_mb":peak/1024/1024,
        "provider_cost_usd":0,"provider":"fixture-local","quality_acceptance":False}
    (ROOT/"phase10"/"benchmark_results.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False))


if __name__=="__main__":main()
