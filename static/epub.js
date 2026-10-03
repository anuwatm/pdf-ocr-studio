"use strict";
window.createEpubWorkspace = ({state, el}) => {
  let loadedJob = null;
  let requestVersion = 0;
  function syncJob() {
    if (loadedJob === state.currentJobId) return;
    loadedJob = state.currentJobId;
    state.epubConfigDirty = false;
    state.epubPreviewRevision = null;
    for (const input of [el.epubTitle, el.epubCreator, el.epubPublisher]) input.value = "";
    el.epubLanguage.value = "th";
    el.epubSourceVariant.value = "auto";
    el.epubChapterSplit.value = "heading";
    el.epubPreviewFrame.srcdoc = "";
    el.epubSourceEditor.value = "";
    el.btnBuildEpub.disabled = true;
    for (const link of [el.btnDlEpub, el.btnDownloadEpub]) link.classList.add("hidden");
  }
  function switchEpubSubtab(subtab) {
    const isPreview = subtab === "preview";
    state.activeEpubSubtab = isPreview ? "preview" : "source";
    el.btnEpubSubtabPreview?.classList.toggle("active", isPreview);
    el.btnEpubSubtabSource?.classList.toggle("active", !isPreview);
    el.epubPreviewView?.classList.toggle("hidden", !isPreview);
    el.epubSourceView?.classList.toggle("hidden", isPreview);
  }

  function collectEpubConfig() {
    return {
      source_variant: el.epubSourceVariant?.value || "auto",
      chapter_split: el.epubChapterSplit?.value || "heading",
      metadata: {
        title: el.epubTitle?.value.trim() || "",
        creator: el.epubCreator?.value.trim() || "",
        publisher: el.epubPublisher?.value.trim() || "",
        language: el.epubLanguage?.value.trim() || "th",
      },
    };
  }

  async function loadEpubPreviewContent(jobId, version) {
    if (!jobId) return;
    const res = await fetch(`/api/jobs/${jobId}/export/epub/preview`, { cache: "no-store" });
    if (!res.ok) return;
    const xhtml = await res.text();
    if (jobId !== state.currentJobId || version !== requestVersion) return;
    if (el.epubPreviewFrame) el.epubPreviewFrame.srcdoc = xhtml;
    if (el.epubSourceEditor) el.epubSourceEditor.value = xhtml;
  }

  async function loadEpubExportStatus() {
    if (!state.currentJobId) return;
    syncJob();
    const jobId = state.currentJobId;
    const version = ++requestVersion;
    try {
      const res = await fetch(`/api/jobs/${state.currentJobId}/export/epub/status`, { cache: "no-store" });
      if (!res.ok) return;
      const status = await res.json();
      if (jobId !== state.currentJobId || version !== requestVersion) return;
      const previewUsable = Boolean(status.preview_ready && !status.is_stale && status.preview_revision && !state.epubConfigDirty);
      state.epubPreviewRevision = previewUsable ? status.preview_revision : null;

      if (el.btnBuildEpub) el.btnBuildEpub.disabled = !previewUsable;
      if (el.epubExportStatusBadge) {
        if (state.epubConfigDirty) {
          el.epubExportStatusBadge.textContent = "ตั้งค่าเปลี่ยน — สร้าง Preview ใหม่";
          el.epubExportStatusBadge.className = "badge badge-warning";
        } else if (status.is_stale || status.package_is_stale) {
          el.epubExportStatusBadge.textContent = "Preview ล้าสมัย — สร้างใหม่";
          el.epubExportStatusBadge.className = "badge badge-warning";
        } else if (status.epub_ready) {
          el.epubExportStatusBadge.textContent = `EPUB พร้อม (${status.chapters_count || 0} บท)`;
          el.epubExportStatusBadge.className = "badge badge-success";
        } else if (status.preview_ready) {
          el.epubExportStatusBadge.textContent = `Preview พร้อม (${status.chapters_count || 0} บท)`;
          el.epubExportStatusBadge.className = "badge badge-code";
        } else {
          el.epubExportStatusBadge.textContent = "ยังไม่ได้ Preview";
          el.epubExportStatusBadge.className = "badge badge-neutral";
        }
      }

      if (status.metadata && !state.epubConfigDirty) {
        if (el.epubTitle && !el.epubTitle.value) el.epubTitle.value = status.metadata.title || "";
        if (el.epubCreator && !el.epubCreator.value) el.epubCreator.value = status.metadata.creator || "";
        if (el.epubPublisher && !el.epubPublisher.value) el.epubPublisher.value = status.metadata.publisher || "";
        if (el.epubLanguage) el.epubLanguage.value = status.metadata.language || "th";
      }
      if (!state.epubConfigDirty && status.source_variant && el.epubSourceVariant) el.epubSourceVariant.value = status.source_variant;
      if (!state.epubConfigDirty && status.chapter_split && el.epubChapterSplit) el.epubChapterSplit.value = status.chapter_split;

      const downloadUrl = `/api/jobs/${state.currentJobId}/export/epub/download`;
      [el.btnDlEpub, el.btnDownloadEpub].forEach(link => {
        if (!link) return;
        link.href = downloadUrl;
        link.classList.toggle("hidden", !status.epub_ready || status.is_stale || state.epubConfigDirty);
      });
      if (status.preview_ready) await loadEpubPreviewContent(jobId, version);
    } catch (err) {
      console.error("Load EPUB status error:", err);
    }
  }

  async function generateEpubPreview() {
    if (!state.currentJobId) return;
    if (state.htmlDirty) { alert("กรุณาบันทึก Final HTML ก่อนสร้าง EPUB Preview"); return; }
    const button = el.btnGenerateEpubPreview;
    const originalText = button?.textContent || "";
    if (button) {
      button.disabled = true;
      button.textContent = "กำลังสร้าง Preview...";
    }
    if (el.btnBuildEpub) el.btnBuildEpub.disabled = true;
    try {
      const res = await fetch(`/api/jobs/${state.currentJobId}/export/epub/preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(collectEpubConfig()),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "สร้าง XHTML Quick Preview ไม่สำเร็จ");
      state.epubConfigDirty = false;
      state.epubPreviewRevision = data.meta?.preview_revision || null;
      await loadEpubExportStatus();
      switchEpubSubtab("preview");
    } catch (err) {
      alert(`สร้าง XHTML Quick Preview ไม่สำเร็จ: ${err.message}`);
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = originalText;
      }
    }
  }

  async function buildEpubPackage() {
    if (state.htmlDirty) { alert("กรุณาบันทึก Final HTML แล้วสร้าง Preview ใหม่ก่อนสร้าง EPUB"); return; }
    if (!state.currentJobId || !state.epubPreviewRevision) {
      alert("กรุณาสร้าง XHTML Quick Preview ก่อน");
      return;
    }
    const button = el.btnBuildEpub;
    const originalText = button?.textContent || "";
    if (button) {
      button.disabled = true;
      button.textContent = "กำลังสร้าง EPUB...";
    }
    try {
      const res = await fetch(`/api/jobs/${state.currentJobId}/export/epub`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ base_preview_revision: state.epubPreviewRevision }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "สร้าง EPUB ไม่สำเร็จ");
      await loadEpubExportStatus();
    } catch (err) {
      alert(`สร้าง EPUB ไม่สำเร็จ: ${err.message}`);
      await loadEpubExportStatus();
    } finally {
      if (button) {
        button.disabled = !state.epubPreviewRevision;
        button.textContent = originalText;
      }
    }
  }

return {switchEpubSubtab, loadEpubExportStatus, generateEpubPreview, buildEpubPackage};
};
