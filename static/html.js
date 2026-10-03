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
    if (saving || generating) { alert("กรุณารอการบันทึกหรือสร้าง HTML ให้เสร็จก่อนเปลี่ยนงาน"); return false; }
    if (dirty() && !confirm("HTML ยังไม่บันทึก ต้องการทิ้งการแก้ไขแล้วเปลี่ยนงานหรือไม่?")) return false;
    return true;
  }
  function syncJob() {
    if (loadedJob === state.currentJobId) return;
    loadedJob = state.currentJobId;
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

  async function loadHtmlExportStatus() {
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
      const displayVariant = hasFinal ? "final" : (hasAi ? "ai" : (hasBasic ? "basic" : null));
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

  async function generateHtmlExport(mode = "basic") {
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

      // Refresh status and load preview
      await loadHtmlExportStatus();
      switchHtmlSubtab("preview");

      if (mode === "ai" && !data.ai_applied) {
        alert("Local AI ออฟไลน์หรือตอบสนองไม่ถูกต้อง ระบบจึงถอยกลับไปใช้ basic.html อย่างปลอดภัย");
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
  return {init, refresh, confirmJobChange, syncJob, switchHtmlSubtab, loadHtmlExportStatus, generateHtmlExport, saveFinalHtml};
};
