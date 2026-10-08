"use strict";
window.createHtmlWorkspace = ({state, el, loadEpubExportStatus}) => {
  let editor;
  let visualEditor;
  let editorMode = "code";
  let savedText = "";
  let loadedJob = null;
  let previewTimer;
  let saving = false;
  let generating = false;
  let requestVersion = 0;
  let aiPollTimer;
  let aiTaskActive = false;
  let handledAiTask = null;
  const aiUi = {
    panel: document.getElementById("html-ai-progress"),
    title: document.getElementById("html-ai-progress-title"),
    detail: document.getElementById("html-ai-progress-detail"),
    error: document.getElementById("html-ai-progress-error"),
    bar: document.getElementById("html-ai-progress-bar"),
    cancel: document.getElementById("btn-cancel-html-ai"),
    retry: document.getElementById("btn-retry-html-ai"),
  };
  const dirty = () => Boolean(editor && editor.getValue() !== savedText);
  function updateDirty() {
    state.htmlDirty = dirty();
    el.htmlSourceStatusText.textContent = dirty() ? "ยังไม่บันทึก • Preview เป็นฉบับร่าง" : "ไม่มีการแก้ไขค้าง • Ctrl+S เพื่อบันทึก Final HTML";
    el.btnSaveFinalHtml.disabled = saving || !state.currentJobId || !editor?.getValue().trim();
  }
  function preview() {
    const doc = new DOMParser().parseFromString(editor.getValue(), "text/html");
    const policy = doc.createElement("meta");
    policy.httpEquiv = "Content-Security-Policy";
    policy.content = "default-src 'none'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; base-uri 'none'; form-action 'none'";
    doc.head.prepend(policy);
    el.htmlPreviewFrame.srcdoc = "<!doctype html>" + doc.documentElement.outerHTML;
  }
  function setContent(value) {
    savedText = value;
    editor.setValue(value);
    editor.clearHistory();
    if (editorMode === "visual") visualEditor.load();
    updateDirty();
    preview();
  }
  function init() {
    editor = CodeMirror.fromTextArea(el.htmlSourceEditor, {
      readOnly: !state.currentJobId, mode: "htmlmixed", lineNumbers: true, indentUnit: 2, tabSize: 2,
      lineWrapping: true, extraKeys: {"Ctrl-S": saveFinalHtml, "Cmd-S": saveFinalHtml},
    });
    visualEditor = createVisualEditor({
      getValue: () => editor.getValue(),
      onChange: value => { if (editor.getValue() !== value) editor.setValue(value); },
      onSave: saveFinalHtml,
      canEdit: () => Boolean(state.currentJobId),
    });
    document.getElementById("html-mode-code").addEventListener("click", () => switchEditorMode("code"));
    document.getElementById("html-mode-visual").addEventListener("click", () => switchEditorMode("visual"));
    editor.on("change", () => {
      editor.save(); updateDirty();
      clearTimeout(previewTimer); previewTimer = setTimeout(preview, 350);
    });
    document.getElementById("html-split-ratio").addEventListener("input", event => {
      document.getElementById("html-split").style.setProperty("--code-width", event.target.value + "%");
      editor.refresh();
    });
    window.addEventListener("beforeunload", event => {
      if (dirty()) { event.preventDefault(); event.returnValue = ""; }
    });
    aiUi.cancel.addEventListener("click", cancelAiExport);
    aiUi.retry.addEventListener("click", () => startAiExport());
    switchHtmlSubtab("source"); updateDirty();
  }
  function switchEditorMode(mode) {
    editorMode = mode;
    document.getElementById("html-code-view").classList.toggle("hidden", mode !== "code");
    document.getElementById("html-visual-view").classList.toggle("hidden", mode !== "visual");
    for (const name of ["code", "visual"]) {
      const button = document.getElementById(`html-mode-${name}`);
      button.classList.toggle("active", name === mode);
      button.setAttribute("aria-pressed", String(name === mode));
    }
    if (mode === "visual") visualEditor.load();
    else refresh();
  }
  function refresh() { requestAnimationFrame(() => editor.refresh()); }
  function confirmJobChange(jobId) {
    if (jobId === state.currentJobId) return true;
    if (saving || (generating && !aiTaskActive)) { alert("กรุณารอการบันทึกหรือสร้าง HTML ให้เสร็จก่อนเปลี่ยนงาน"); return false; }
    if (dirty() && !confirm("HTML ยังไม่บันทึก ต้องการทิ้งการแก้ไขแล้วเปลี่ยนงานหรือไม่?")) return false;
    return true;
  }
  function syncJob() {
    if (loadedJob === state.currentJobId) return;
    loadedJob = state.currentJobId;
    clearTimeout(aiPollTimer);
    generating = false;
    aiTaskActive = false;
    handledAiTask = null;
    aiUi.panel.classList.add("hidden");
    el.btnGenerateHtmlAi.disabled = false;
    el.btnGenerateHtmlAi.textContent = "สร้าง HTML พร้อม AI";
    el.btnGenerateHtmlBasic.disabled = false;
    if (loadedJob) pollAiProgress(loadedJob);
    editor.setOption("readOnly", !loadedJob);
    requestVersion++;
    setContent("");
  }
  function switchHtmlSubtab(subtab) {
    state.activeHtmlSubtab = subtab;
    const isPreview = subtab === "preview";
    el.btnSubtabPreview.classList.toggle("active", isPreview);
    el.btnSubtabSource.classList.toggle("active", !isPreview);
    document.getElementById("html-split").dataset.mobileView = subtab;
    refresh();
  }

  async function loadHtmlExportStatus(preferredVariant = null) {
    if (!state.currentJobId) return;
    syncJob();
    const jobId = state.currentJobId;
    const version = ++requestVersion;
    try {
      const res = await fetch(`/api/jobs/${jobId}/export/html/status`);
      if (!res.ok) return;
      const status = await res.json();
      if (jobId !== state.currentJobId || version !== requestVersion) return;
      if (!dirty() && !saving) state.htmlBaseRevision = status.source_revision || 1;

      // Update badge
      if (el.htmlExportStatusBadge) {
        if (status.is_stale) {
          el.htmlExportStatusBadge.textContent = "ต้องสร้างใหม่ (ข้อความเปลี่ยน)";
          el.htmlExportStatusBadge.className = "badge badge-warning";
        } else if (status.variants && status.variants.length > 0) {
          el.htmlExportStatusBadge.textContent = `ส่งออกแล้ว (${status.variants.join(", ")})`;
          el.htmlExportStatusBadge.className = "badge badge-success";
        } else {
          el.htmlExportStatusBadge.textContent = "ยังไม่ได้ส่งออก";
          el.htmlExportStatusBadge.className = "badge badge-neutral";
        }
      }

      // Update variant download links in toolbar
      const variants = (status.variants && status.variants.length > 0)
        ? status.variants
        : [
            status.has_final ? "final" : null,
            status.has_ai ? "ai" : null,
            status.has_basic ? "basic" : null,
          ].filter(Boolean);
      const hasBasic = variants.includes("basic");
      const hasAi = variants.includes("ai");
      const hasFinal = variants.includes("final");

      if (el.btnDlHtmlBasic) {
        el.btnDlHtmlBasic.href = `/api/jobs/${state.currentJobId}/export/html/basic`;
        el.btnDlHtmlBasic.classList.toggle("hidden", !hasBasic);
      }
      if (el.btnDlHtmlAi) {
        el.btnDlHtmlAi.href = `/api/jobs/${state.currentJobId}/export/html/ai`;
        el.btnDlHtmlAi.classList.toggle("hidden", !hasAi);
      }
      if (el.btnDlHtmlFinal) {
        el.btnDlHtmlFinal.href = `/api/jobs/${state.currentJobId}/export/html/final`;
        el.btnDlHtmlFinal.classList.toggle("hidden", !hasFinal);
      }

      // Bottom bar download link (prefer final, then ai, then basic)
      if (el.btnDownloadHtml) {
        const preferred = hasFinal ? "final" : (hasAi ? "ai" : (hasBasic ? "basic" : null));
        if (preferred) {
          el.btnDownloadHtml.href = `/api/jobs/${state.currentJobId}/export/html/${preferred}`;
          el.btnDownloadHtml.classList.remove("hidden");
        } else {
          el.btnDownloadHtml.classList.add("hidden");
        }
      }

      // Determine preferred variant to display in preview and source editor
      const displayVariant = preferredVariant && variants.includes(preferredVariant)
        ? preferredVariant
        : (hasFinal ? "final" : (hasAi ? "ai" : (hasBasic ? "basic" : null)));
      if (dirty() || saving) return;
      if (displayVariant) {
        state.currentHtmlVariant = displayVariant;
        await loadHtmlVariantContent(displayVariant, jobId, version);
      } else {
        if (el.htmlPreviewFrame) {
          el.htmlPreviewFrame.srcdoc = "<div style='font-family:sans-serif;padding:2rem;color:#888;text-align:center;'>ยังไม่ได้ส่งออก HTML กรุณากดปุ่ม 'สร้าง HTML พื้นฐาน' หรือ 'สร้าง HTML พร้อม AI' ด้านบน</div>";
        }
        setContent("");
      }
    } catch (err) {
      console.error("Load HTML export status error:", err);
    }
  }

  async function loadHtmlVariantContent(variant, jobId, version) {
    const res = await fetch(`/api/jobs/${jobId}/export/html/${variant}`);
    if (!res.ok) throw new Error("โหลด HTML ไม่สำเร็จ");
    const content = await res.text();
    if (jobId !== state.currentJobId || version !== requestVersion || dirty() || saving) return;
    if (content !== savedText) setContent(content);
  }

  async function loadStructuredHtml() {
    if (!state.currentJobId) throw new Error("ยังไม่ได้เลือกงาน OCR");
    if (dirty() && !confirm("HTML ยังไม่บันทึก ต้องการทิ้งฉบับร่างแล้วเปิด Structured HTML หรือไม่?")) return false;
    syncJob();
    const jobId = state.currentJobId;
    const version = ++requestVersion;
    const [structuredStatusResponse, htmlStatusResponse] = await Promise.all([
      fetch(`/api/jobs/${jobId}/export/structured/status`, {cache: "no-store"}),
      fetch(`/api/jobs/${jobId}/export/html/status`, {cache: "no-store"}),
    ]);
    if (!structuredStatusResponse.ok || !htmlStatusResponse.ok) throw new Error("อ่านสถานะ HTML ไม่สำเร็จ");
    const structuredStatus = await structuredStatusResponse.json();
    const htmlStatus = await htmlStatusResponse.json();
    if (structuredStatus.status === "stale") throw new Error("Structured HTML ล้าสมัย กรุณาสร้างใหม่ก่อนแก้ไข");
    if (structuredStatus.status !== "ready") throw new Error("ยังไม่มี Structured HTML กรุณาสร้างก่อน");
    const response = await fetch(`/api/jobs/${jobId}/export/structured/html`, {cache: "no-store"});
    if (!response.ok) throw new Error("โหลด Structured HTML ไม่สำเร็จ");
    const content = await response.text();
    if (jobId !== state.currentJobId || version !== requestVersion) return false;
    state.htmlBaseRevision = htmlStatus.source_revision || structuredStatus.current_source_revision || 1;
    state.currentHtmlVariant = "structured";
    setContent(content);
    el.htmlExportStatusBadge.textContent = "เปิด Structured HTML แล้ว";
    el.htmlExportStatusBadge.className = "badge badge-success";
    switchHtmlSubtab("source");
    refresh();
    return true;
  }

  function duration(seconds) {
    const total = Math.max(0, Math.floor(seconds || 0));
    return `${Math.floor(total / 60).toString().padStart(2, "0")}:${(total % 60).toString().padStart(2, "0")}`;
  }
  function renderAiProgress(task) {
    aiUi.panel.classList.remove("hidden");
    aiTaskActive = ["running", "cancelling"].includes(task.status);
    generating = aiTaskActive;
    el.btnGenerateHtmlAi.disabled = aiTaskActive;
    el.btnGenerateHtmlBasic.disabled = aiTaskActive;
    el.btnGenerateHtmlAi.textContent = aiTaskActive ? "กำลังสร้าง HTML ด้วย AI…" : "สร้าง HTML พร้อม AI";
    const total = task.chunk_count || 0;
    const completed = task.completed_chunks || 0;
    const current = task.current_chunk || 0;
    if (total) { aiUi.bar.max = total; aiUi.bar.value = completed; }
    else aiUi.bar.removeAttribute("value");
    let title;
    if (task.status === "completed") title = `สร้าง HTML สำเร็จ · ครบ ${completed}/${total} ชุด`;
    else if (task.status === "failed") title = "สร้าง HTML ด้วย AI ไม่สำเร็จ";
    else if (task.status === "cancelled") title = "ยกเลิกการสร้าง HTML ด้วย AI แล้ว";
    else if (task.status === "cancelling") title = "กำลังยกเลิก · รอคำตอบชุดปัจจุบันแล้วหยุด";
    else if (task.stage === "waiting_ai") title = `รอ AI ตอบกลับ · ชุด ${current}/${total} · สำเร็จ ${completed} ชุด`;
    else if (task.stage === "validating") title = "ประมวลผลครบแล้ว · กำลังตรวจโครงสร้าง HTML";
    else if (task.stage === "publishing") title = "กำลังบันทึกไฟล์ HTML";
    else if (task.stage === "checking_ai") title = "กำลังตรวจการเชื่อมต่อ Local AI";
    else if (task.stage === "preparing") title = "กำลังเตรียมและแบ่งข้อความ";
    else title = `กำลังประมวลผล · สำเร็จ ${completed}/${total} ชุด`;
    if (aiUi.title.textContent !== title) aiUi.title.textContent = title;
    aiUi.detail.textContent = `ใช้เวลา ${duration(task.elapsed_seconds)} · ได้รับสถานะล่าสุดเมื่อ ${Math.floor(task.last_update_seconds || 0)} วินาทีก่อน`
      + (task.stage === "waiting_ai" ? ` · รอ ${duration(task.waiting_seconds)} / timeout ${task.timeout_seconds} วินาทีต่อชุด` : "");
    const error = task.status === "failed" ? (task.error || "ไม่ทราบสาเหตุ") : "";
    aiUi.error.textContent = error + (error && task.meta?.failed_chunk ? ` (ชุดที่ ${task.meta.failed_chunk}/${total})` : "");
    aiUi.error.classList.toggle("hidden", !error);
    aiUi.cancel.classList.toggle("hidden", !aiTaskActive);
    aiUi.cancel.disabled = task.status === "cancelling";
    aiUi.retry.classList.toggle("hidden", !["failed", "cancelled"].includes(task.status));
  }
  async function pollAiProgress(jobId) {
    clearTimeout(aiPollTimer);
    if (jobId !== state.currentJobId) return;
    try {
      const res = await fetch(`/api/jobs/${jobId}/export/html/ai/progress`, {cache: "no-store"});
      if (!res.ok) throw new Error(`อ่านสถานะไม่สำเร็จ (HTTP ${res.status})`);
      const task = await res.json();
      if (jobId !== state.currentJobId) return;
      if (!task.status || task.status === "idle") return;
      const wasActive = aiTaskActive;
      renderAiProgress(task);
      if (aiTaskActive) {
        sessionStorage.setItem("htmlAiJobId", jobId);
        aiPollTimer = setTimeout(() => pollAiProgress(jobId), 2000);
      } else {
        if (sessionStorage.getItem("htmlAiJobId") === jobId) sessionStorage.removeItem("htmlAiJobId");
        if (wasActive && handledAiTask !== task.task_id) {
          handledAiTask = task.task_id;
          await loadHtmlExportStatus(task.status === "completed" ? "ai" : "basic");
          switchHtmlSubtab("preview");
        }
      }
    } catch (error) {
      if (jobId !== state.currentJobId) return;
      aiUi.panel.classList.remove("hidden");
      aiUi.detail.textContent = `${error.message} · กำลังลองเชื่อมต่อสถานะใหม่ งานอาจยังประมวลผลอยู่`;
      aiPollTimer = setTimeout(() => pollAiProgress(jobId), 3000);
    }
  }
  async function startAiExport() {
    if (!state.currentJobId || saving || generating) return;
    if (dirty()) { alert("กรุณาบันทึก HTML ที่แก้ไขก่อนสร้างใหม่"); return; }
    const jobId = state.currentJobId;
    generating = true;
    el.btnGenerateHtmlAi.disabled = true;
    try {
      const res = await fetch(`/api/jobs/${jobId}/export/html/ai/start`, {method: "POST"});
      const task = await res.json();
      if (!res.ok) throw new Error(task.detail || "เริ่มงาน AI ไม่สำเร็จ");
      if (jobId !== state.currentJobId) return;
      renderAiProgress(task);
      sessionStorage.setItem("htmlAiJobId", jobId);
      pollAiProgress(jobId);
    } catch (error) {
      if (jobId !== state.currentJobId) return;
      generating = false;
      el.btnGenerateHtmlAi.disabled = false;
      aiUi.panel.classList.remove("hidden");
      aiUi.title.textContent = "เริ่มงาน AI ไม่สำเร็จ";
      aiUi.error.textContent = error.message;
      aiUi.error.classList.remove("hidden");
      aiUi.retry.classList.remove("hidden");
    }
  }
  async function cancelAiExport() {
    const jobId = state.currentJobId;
    if (!jobId || !aiTaskActive) return;
    aiUi.cancel.disabled = true;
    try {
      const res = await fetch(`/api/jobs/${jobId}/export/html/ai/cancel`, {method: "POST"});
      const task = await res.json();
      if (!res.ok) throw new Error(task.detail || "ยกเลิกงานไม่สำเร็จ");
      if (jobId !== state.currentJobId) return;
      renderAiProgress(task);
      pollAiProgress(jobId);
    } catch (error) {
      aiUi.error.textContent = error.message;
      aiUi.error.classList.remove("hidden");
      aiUi.cancel.disabled = false;
    }
  }
  async function generateHtmlExport(mode = "basic") {
    if (mode === "ai") return startAiExport();
    if (!state.currentJobId || saving || generating) return;
    if (dirty()) { alert("กรุณาบันทึก HTML ที่แก้ไขก่อนสร้างใหม่"); return; }
    generating = true;
    const btn = mode === "ai" ? el.btnGenerateHtmlAi : el.btnGenerateHtmlBasic;
    const originalText = btn ? btn.textContent : "";
    if (btn) {
      btn.disabled = true;
      btn.textContent = mode === "ai" ? "กำลังประมวลผล AI..." : "กำลังสร้าง HTML...";
    }

    try {
      const res = await fetch(`/api/jobs/${state.currentJobId}/export/html`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: mode }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Export HTML failed");
      }
      const data = await res.json();
      const aiApplied = data.ai_applied === true || data.status === "passed";

      // Refresh status and load preview
      await loadHtmlExportStatus(mode === "ai" && aiApplied ? "ai" : "basic");
      switchHtmlSubtab("preview");

      if (mode === "ai" && !aiApplied) {
        const reason = data.meta?.error || data.meta?.validator_reason || data.detail || data.meta?.message || data.status;
        const batch = data.meta?.failed_chunk ? ` (ชุดที่ ${data.meta.failed_chunk}/${data.meta.chunk_count})` : "";
        alert(`สร้าง HTML ด้วย AI ไม่สำเร็จ${batch}: ${reason}\nแสดง basic.html แทน`);
      }
    } catch (err) {
      alert(`สร้าง HTML ไม่สำเร็จ: ${err.message}`);
    } finally {
      generating = false;
      if (btn) {
        btn.disabled = false;
        btn.textContent = originalText;
      }
    }
  }

  async function saveFinalHtml() {
    if (!state.currentJobId || saving || generating) return;
    const htmlContent = editor.getValue();
    if (!htmlContent.trim()) { alert("เนื้อหา HTML ว่างเปล่า"); return; }
    const jobId = state.currentJobId;
    const baseRevision = state.htmlBaseRevision;
    saving = true; updateDirty();
    el.btnSaveFinalHtml.textContent = "กำลังบันทึก...";
    const send = overwrite => fetch(`/api/jobs/${jobId}/export/html/final`, {
      method: "PUT", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({html_content: htmlContent, base_revision: baseRevision, overwrite}),
    });
    try {
      let res = await send(false);
      if (res.status === 409) {
        if (!confirm("ไฟล์ต้นทางเปลี่ยนไปแล้ว ต้องการบันทึกทับ Final HTML หรือไม่?")) return;
        res = await send(true);
      }
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail || "Save final HTML failed"); }
      if (jobId !== state.currentJobId) return;
      savedText = htmlContent;
      saving = false; updateDirty();
      await loadHtmlExportStatus();
      el.epubSourceVariant.value = "final";
      state.epubConfigDirty = true;
      await loadEpubExportStatus();
    } catch (err) { alert(`บันทึก final.html ไม่สำเร็จ: ${err.message}`); }
    finally { saving = false; updateDirty(); el.btnSaveFinalHtml.textContent = "บันทึก Final HTML"; }
  }
  return {init, refresh, confirmJobChange, syncJob, switchHtmlSubtab, loadHtmlExportStatus, loadStructuredHtml, generateHtmlExport, saveFinalHtml};
};
