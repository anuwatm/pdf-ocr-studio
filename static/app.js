/**
 * OneOCR Thai Web Studio - Client Application (Phase 5)
 * Coordinates upload, job queue, dual-pane document viewer,
 * interactive bounding box highlighting, AI diff review,
 * manual text editing with conflict detection, and downloads.
 */

(() => {
  "use strict";

  // Application State
  const state = {
    selectedFile: null,
    uploadedJob: null,
    currentJobId: null,
    jobStatus: null,
    currentPageNum: 1,
    currentPageData: null,
    currentRevision: 1,
    hasUnsavedChanges: false,
    unsavedText: "",
    zoomLevel: 1.0,
    aiConnected: false,
    pollTimer: null,
    activeBoxIndex: null,
  };

  // DOM Elements
  const el = {
    themeToggle: document.getElementById("btn-theme-toggle"),
    aiStatusBadge: document.getElementById("ai-status-badge"),
    aiStatusText: document.getElementById("ai-status-text"),
    aiAvailableBadge: document.getElementById("ai-available-badge"),
    modeOcrAi: document.getElementById("mode-ocr-ai"),
    modeOcrOnly: document.getElementById("mode-ocr-only"),

    // Upload
    dropzone: document.getElementById("dropzone"),
    fileInput: document.getElementById("file-input"),
    fileSelectedBox: document.getElementById("file-selected-box"),
    selectedFileName: document.getElementById("selected-file-name"),
    selectedFileSize: document.getElementById("selected-file-size"),
    selectedFileIcon: document.getElementById("selected-file-icon"),
    btnRemoveFile: document.getElementById("btn-remove-file"),
    btnStartJob: document.getElementById("btn-start-job"),
    pageOptions: document.getElementById("page-options"),
    pdfPageSummary: document.getElementById("pdf-page-summary"),
    inputPageCount: document.getElementById("input-page-count"),
    pageCountLimit: document.getElementById("page-count-limit"),

    // Progress Section
    sectionProgress: document.getElementById("section-progress"),
    jobIdBadge: document.getElementById("job-id-badge"),
    jobStatusBadge: document.getElementById("job-status-badge"),
    jobAttemptBadge: document.getElementById("job-attempt-badge"),
    progressBarFill: document.getElementById("progress-bar-fill"),
    progressTextPages: document.getElementById("progress-text-pages"),
    progressTextPercent: document.getElementById("progress-text-percent"),
    btnCancelJob: document.getElementById("btn-cancel-job"),
    btnRetryJob: document.getElementById("btn-retry-job"),
    retryMenu: document.getElementById("retry-menu"),
    jobAlertBanner: document.getElementById("job-alert-banner"),
    jobAlertTitle: document.getElementById("job-alert-title"),
    jobAlertMsg: document.getElementById("job-alert-msg"),

    // Workspace Section
    sectionWorkspace: document.getElementById("section-workspace"),
    btnPrevPage: document.getElementById("btn-prev-page"),
    btnNextPage: document.getElementById("btn-next-page"),
    pageSelect: document.getElementById("page-select"),
    pageTotalLabel: document.getElementById("page-total-label"),
    badgePageReviewStatus: document.getElementById("badge-page-review-status"),
    btnMarkReviewed: document.getElementById("btn-mark-reviewed"),

    // Viewer
    refImage: document.getElementById("ref-image"),
    imageViewport: document.getElementById("image-viewport"),
    bboxOverlay: document.getElementById("bbox-overlay"),
    btnZoomIn: document.getElementById("btn-zoom-in"),
    btnZoomOut: document.getElementById("btn-zoom-out"),
    btnZoomReset: document.getElementById("btn-zoom-reset"),

    // Tabs
    tabFinal: document.getElementById("tab-final"),
    tabDiff: document.getElementById("tab-diff"),
    tabRaw: document.getElementById("tab-raw"),
    panelFinal: document.getElementById("panel-final"),
    panelDiff: document.getElementById("panel-diff"),
    panelRaw: document.getElementById("panel-raw"),
    badgeProposalsCount: document.getElementById("badge-proposals-count"),

    // Editor & Diff
    editorFinalText: document.getElementById("editor-final-text"),
    viewerRawText: document.getElementById("viewer-raw-text"),
    revisionBadge: document.getElementById("revision-badge"),
    saveIndicator: document.getElementById("save-indicator"),
    saveStatusText: document.getElementById("save-status-text"),
    btnSaveEdit: document.getElementById("btn-save-edit"),

    metricLevenshtein: document.getElementById("metric-levenshtein"),
    metricSubstitutions: document.getElementById("metric-substitutions"),
    metricInsertions: document.getElementById("metric-insertions"),
    metricDeletions: document.getElementById("metric-deletions"),
    btnAcceptAll: document.getElementById("btn-accept-all"),
    btnRevertAll: document.getElementById("btn-revert-all"),
    proposalsList: document.getElementById("proposals-list"),

    // Downloads
    downloadWarningBanner: document.getElementById("download-warning-banner"),
    btnDownloadRaw: document.getElementById("btn-download-raw"),
    btnDownloadCorrected: document.getElementById("btn-download-corrected"),
    btnDownloadFinal: document.getElementById("btn-download-final"),
    btnDownloadBundle: document.getElementById("btn-download-bundle"),

    // Conflict Modal
    modalConflict: document.getElementById("modal-conflict"),
    modalConflictText: document.getElementById("modal-conflict-text"),
    conflictUnsavedText: document.getElementById("conflict-unsaved-text"),
    btnConflictCopy: document.getElementById("btn-conflict-copy"),
    btnConflictReload: document.getElementById("btn-conflict-reload"),
  };

  /* ==========================================================================
     Initialization & Health Checks
     ========================================================================== */

  function init() {
    setupTheme();
    setupDropzone();
    setupEventListeners();
    checkAiStatus();
    setInterval(checkAiStatus, 10000);
  }

  // Theme Management
  function setupTheme() {
    const savedTheme = localStorage.getItem("theme") || "theme-dark";
    document.body.className = savedTheme;

    el.themeToggle.addEventListener("click", () => {
      const isDark = document.body.classList.contains("theme-dark");
      const newTheme = isDark ? "theme-light" : "theme-dark";
      document.body.className = newTheme;
      localStorage.setItem("theme", newTheme);
    });
  }

  // Check Local LLM Status
  async function checkAiStatus() {
    try {
      const res = await fetch("/api/ai/status");
      if (!res.ok) throw new Error("AI service unavailable");
      const data = await res.json();

      if (data.status === "connected") {
        state.aiConnected = true;
        el.aiStatusBadge.className = "status-badge status-online";
        el.aiStatusText.textContent = `Online: ${data.configured_model}`;
        el.aiAvailableBadge.className = "badge badge-success";
        el.aiAvailableBadge.textContent = "พร้อมใช้งาน";
      } else {
        state.aiConnected = false;
        el.aiStatusBadge.className = "status-badge status-offline";
        el.aiStatusText.textContent = "Offline (Local AI ไม่พร้อม)";
        el.aiAvailableBadge.className = "badge badge-warning";
        el.aiAvailableBadge.textContent = "ออฟไลน์";
      }
    } catch {
      state.aiConnected = false;
      el.aiStatusBadge.className = "status-badge status-offline";
      el.aiStatusText.textContent = "Offline: Local AI 127.0.0.1:1234";
      el.aiAvailableBadge.className = "badge badge-warning";
      el.aiAvailableBadge.textContent = "ออฟไลน์";
    }
  }

  /* ==========================================================================
     File Upload & Dropzone
     ========================================================================== */

  function setupDropzone() {
    el.dropzone.addEventListener("click", () => el.fileInput.click());

    el.fileInput.addEventListener("change", (e) => {
      if (e.target.files && e.target.files[0]) {
        handleFileSelect(e.target.files[0]);
      }
    });

    ["dragenter", "dragover"].forEach(evt => {
      el.dropzone.addEventListener(evt, (e) => {
        e.preventDefault();
        el.dropzone.classList.add("dragover");
      });
    });

    ["dragleave", "drop"].forEach(evt => {
      el.dropzone.addEventListener(evt, (e) => {
        e.preventDefault();
        el.dropzone.classList.remove("dragover");
      });
    });

    el.dropzone.addEventListener("drop", (e) => {
      if (e.dataTransfer.files && e.dataTransfer.files[0]) {
        handleFileSelect(e.dataTransfer.files[0]);
      }
    });

    el.btnRemoveFile.addEventListener("click", resetFileSelection);
  }

  function handleFileSelect(file) {
    const ext = file.name.substring(file.name.lastIndexOf(".")).toLowerCase();
    const allowed = [".pdf", ".png", ".jpg", ".jpeg"];

    if (!allowed.includes(ext)) {
      alert(`ไฟล์ชนิด '${ext}' ไม่ได้รับการรองรับ กรุณาเลือกไฟล์ PDF หรือภาพ (PNG, JPG)`);
      return;
    }

    if (file.size > 50 * 1024 * 1024) {
      alert("ไฟล์มีขนาดเกินเพดาน 50 MB กรุณาเลือกไฟล์ที่มีขนาดเล็กกว่า 50 MB");
      return;
    }

    state.selectedFile = file;
    state.uploadedJob = null;
    el.selectedFileName.textContent = file.name;
    el.selectedFileSize.textContent = formatBytes(file.size);
    el.selectedFileIcon.textContent = ext.replace(".", "").toUpperCase();

    el.dropzone.classList.add("hidden");
    el.fileSelectedBox.classList.remove("hidden");
    el.btnStartJob.disabled = false;
    el.btnStartJob.innerHTML = "<span>ตรวจสอบจำนวนหน้า</span>";
    el.pageOptions.classList.add("hidden");
  }

  function resetFileSelection() {
    state.selectedFile = null;
    state.uploadedJob = null;
    el.fileInput.value = "";
    el.fileSelectedBox.classList.add("hidden");
    el.dropzone.classList.remove("hidden");
    el.btnStartJob.disabled = true;
    el.btnStartJob.innerHTML = "<span>ตรวจสอบจำนวนหน้า</span>";
    el.pageOptions.classList.add("hidden");
  }

  function formatBytes(bytes) {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
  }

  /* ==========================================================================
     Job Start & Progress Polling
     ========================================================================== */

  function setupEventListeners() {
    el.btnStartJob.addEventListener("click", startJobFlow);
    el.inputPageCount.addEventListener("input", () => {
      if (!state.uploadedJob) return;
      const value = Number.parseInt(el.inputPageCount.value, 10);
      const max = Number.parseInt(el.inputPageCount.max, 10);
      if (Number.isInteger(value) && value >= 1 && value <= max) {
        el.btnStartJob.innerHTML = `<span>เริ่มแปลง ${value} หน้า</span>`;
      }
    });
    el.btnCancelJob.addEventListener("click", cancelCurrentJob);

    // Retry dropdown toggle
    el.btnRetryJob.addEventListener("click", (e) => {
      e.stopPropagation();
      el.retryMenu.classList.toggle("hidden");
    });
    document.addEventListener("click", () => el.retryMenu.classList.add("hidden"));

    document.querySelectorAll(".dropdown-item[data-retry-mode]").forEach(btn => {
      btn.addEventListener("click", (e) => {
        const mode = e.target.getAttribute("data-retry-mode");
        retryCurrentJob(mode);
      });
    });

    // Page navigation
    el.btnPrevPage.addEventListener("click", () => switchPage(state.currentPageNum - 1));
    el.btnNextPage.addEventListener("click", () => switchPage(state.currentPageNum + 1));
    el.pageSelect.addEventListener("change", (e) => switchPage(parseInt(e.target.value, 10)));

    // Zoom controls
    el.btnZoomIn.addEventListener("click", () => setZoom(state.zoomLevel + 0.15));
    el.btnZoomOut.addEventListener("click", () => setZoom(state.zoomLevel - 0.15));
    el.btnZoomReset.addEventListener("click", () => setZoom(1.0));

    // Tabs
    el.tabFinal.addEventListener("click", () => activateTab("final"));
    el.tabDiff.addEventListener("click", () => activateTab("diff"));
    el.tabRaw.addEventListener("click", () => activateTab("raw"));

    // Save & Edit
    el.btnSaveEdit.addEventListener("click", saveManualEdit);
    el.editorFinalText.addEventListener("input", () => {
      state.hasUnsavedChanges = true;
      state.unsavedText = el.editorFinalText.value;
      updateSaveIndicator("unsaved");
    });

    // Keyboard shortcut: Ctrl+S to save (does not break Tab/focus navigation)
    document.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        e.preventDefault();
        saveManualEdit();
      }
    });

    // Mark as reviewed
    el.btnMarkReviewed.addEventListener("click", markAsReviewed);

    // Batch Diff Actions
    el.btnAcceptAll.addEventListener("click", acceptAllCorrections);
    el.btnRevertAll.addEventListener("click", revertAllCorrections);

    // Conflict Modal Actions
    el.btnConflictCopy.addEventListener("click", () => {
      navigator.clipboard.writeText(state.unsavedText);
      alert("คัดลอกข้อความของคุณเรียบร้อยแล้ว");
    });
    el.btnConflictReload.addEventListener("click", () => {
      el.modalConflict.classList.add("hidden");
      loadPageData(state.currentJobId, state.currentPageNum);
    });
  }

  async function startJobFlow() {
    if (!state.selectedFile) return;

    el.btnStartJob.disabled = true;

    try {
      if (!state.uploadedJob) {
        el.btnStartJob.innerHTML = "<span>กำลังอัปโหลด...</span>";
        const formData = new FormData();
        formData.append("file", state.selectedFile);

        const upRes = await fetch("/api/upload", { method: "POST", body: formData });
        if (!upRes.ok) {
          const err = await upRes.json();
          throw new Error(err.detail || "Upload failed");
        }
        state.uploadedJob = await upRes.json();
        const sourcePages = state.uploadedJob.total_pages;
        const allowedPages = Math.min(sourcePages, 100);
        el.pdfPageSummary.textContent = `เอกสารนี้มี ${sourcePages} หน้า`;
        el.inputPageCount.min = "1";
        el.inputPageCount.max = String(allowedPages);
        el.inputPageCount.value = String(allowedPages);
        el.inputPageCount.disabled = false;
        el.pageCountLimit.textContent = `หน้า (เลือกได้ 1–${allowedPages})`;
        el.pageOptions.classList.remove("hidden");
        el.btnStartJob.disabled = false;
        el.btnStartJob.innerHTML = `<span>เริ่มแปลง ${allowedPages} หน้า</span>`;
        return;
      }

      const selectedPages = Number.parseInt(el.inputPageCount.value, 10);
      const maximumPages = Number.parseInt(el.inputPageCount.max, 10);
      if (!Number.isInteger(selectedPages) || selectedPages < 1 || selectedPages > maximumPages) {
        throw new Error(`กรุณาเลือกจำนวนหน้าระหว่าง 1 ถึง ${maximumPages}`);
      }

      el.btnStartJob.innerHTML = "<span>กำลังเริ่มงาน...</span>";
      const enableAi = el.modeOcrAi.checked;
      state.currentJobId = state.uploadedJob.job_id;
      const startRes = await fetch(`/api/jobs/${state.currentJobId}/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enable_ai: enableAi, max_pages: selectedPages }),
      });
      if (!startRes.ok) {
        const err = await startRes.json();
        throw new Error(err.detail || "Failed to start job");
      }

      // 3. Show Progress & Workspace
      el.sectionProgress.classList.remove("hidden");
      el.jobIdBadge.textContent = state.currentJobId;
      startStatusPolling();
    } catch (err) {
      alert(`เกิดข้อผิดพลาด: ${err.message}`);
      el.btnStartJob.disabled = false;
      el.btnStartJob.innerHTML = state.uploadedJob
        ? `<span>เริ่มแปลง ${el.inputPageCount.value} หน้า</span>`
        : "<span>ตรวจสอบจำนวนหน้า</span>";
    }
  }

  function startStatusPolling() {
    if (state.pollTimer) clearInterval(state.pollTimer);
    pollJobStatus();
    state.pollTimer = setInterval(pollJobStatus, 800);
  }

  async function pollJobStatus() {
    if (!state.currentJobId) return;

    try {
      const res = await fetch(`/api/jobs/${state.currentJobId}/status`);
      if (!res.ok) return;
      const job = await res.json();
      state.jobStatus = job;

      updateProgressUI(job);

      // Populate page selector if total_pages changed
      if (el.pageSelect.children.length !== job.total_pages) {
        updatePageSelector(job.total_pages);
      }

      // If at least one page completed, show workspace
      const hasCompletedPages = job.pages.some(p => p.status === "completed" || p.status === "blank");
      if (hasCompletedPages && el.sectionWorkspace.classList.contains("hidden")) {
        el.sectionWorkspace.classList.remove("hidden");
        switchPage(1);
      } else if (hasCompletedPages && !state.currentPageData) {
        switchPage(1);
      }

      // Update downloads
      updateDownloadLinks(job);

      // Stop polling when terminal state reached
      const terminal = ["completed", "partial", "failed", "cancelled"];
      if (terminal.includes(job.status)) {
        clearInterval(state.pollTimer);
        state.pollTimer = null;
        // Refresh current page once finished
        if (state.currentPageNum) {
          loadPageData(state.currentJobId, state.currentPageNum);
        }
      }
    } catch (err) {
      console.error("Status poll error:", err);
    }
  }

  function updateProgressUI(job) {
    el.jobIdBadge.textContent = job.job_id;
    el.jobAttemptBadge.textContent = `Attempt ${job.current_attempt}`;

    // Status badge
    el.jobStatusBadge.textContent = job.status;
    el.jobStatusBadge.className = `badge badge-${getStatusBadgeType(job.status)}`;

    // Progress bar
    const total = job.total_pages || 1;
    const completed = job.completed_pages || 0;
    const pct = Math.round((completed / total) * 100);

    el.progressBarFill.style.width = `${pct}%`;
    el.progressTextPages.textContent = `ประมวลผลแล้ว ${completed} / ${total} หน้า`;
    el.progressTextPercent.textContent = `${pct}%`;

    // Action buttons
    if (job.status === "queued" || job.status === "running") {
      el.btnCancelJob.classList.remove("hidden");
      el.btnRetryJob.classList.add("hidden");
    } else {
      el.btnCancelJob.classList.add("hidden");
      el.btnRetryJob.classList.remove("hidden");
    }

    // Error banner
    if (job.error_message || job.status === "failed" || job.status === "partial") {
      el.jobAlertBanner.classList.remove("hidden");
      el.jobAlertTitle.textContent = job.status === "failed" ? "การประมวลผลล้มเหลว" : "ประมวลผลเสร็จสิ้นบางส่วน";
      el.jobAlertMsg.textContent = job.error_message || "มีบางหน้าพบข้อผิดพลาด กรุณาตรวจสอบสถานะรายหน้า";
    } else {
      el.jobAlertBanner.classList.add("hidden");
    }
  }

  function getStatusBadgeType(status) {
    switch (status) {
      case "completed": return "success";
      case "running": case "queued": return "status";
      case "partial": case "in_review": return "warning";
      case "failed": return "danger";
      default: return "neutral";
    }
  }

  async function cancelCurrentJob() {
    if (!state.currentJobId) return;
    if (!confirm("คุณแน่ใจหรือไม่ว่าต้องการยกเลิกงานนี้?")) return;

    try {
      await fetch(`/api/jobs/${state.currentJobId}/cancel`, { method: "POST" });
      pollJobStatus();
    } catch (err) {
      alert(`ยกเลิกงานไม่สำเร็จ: ${err.message}`);
    }
  }

  async function retryCurrentJob(retryMode = "failed_only") {
    if (!state.currentJobId) return;

    try {
      const res = await fetch(`/api/jobs/${state.currentJobId}/retry`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ retry_mode: retryMode }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Retry failed");
      }
      startStatusPolling();
    } catch (err) {
      alert(`เริ่มใหม่ไม่สำเร็จ: ${err.message}`);
    }
  }

  /* ==========================================================================
     Dual-Pane Workspace: Page Viewer & Image Overlays
     ========================================================================== */

  function updatePageSelector(totalPages) {
    el.pageSelect.innerHTML = "";
    for (let i = 1; i <= totalPages; i++) {
      const opt = document.createElement("option");
      opt.value = i;
      opt.textContent = i;
      el.pageSelect.appendChild(opt);
    }
    el.pageTotalLabel.textContent = `จาก ${totalPages}`;
  }

  async function switchPage(pageNum) {
    if (!state.jobStatus) return;
    const total = state.jobStatus.total_pages;
    if (pageNum < 1 || pageNum > total) return;

    // Check unsaved changes before switching
    if (state.hasUnsavedChanges) {
      if (!confirm("คุณมีการแก้ไขที่ยังไม่ได้บันทึก หากเปลี่ยนหน้าข้อความที่แก้ไขจะหายไป ต้องการเปลี่ยนหน้าหรือไม่?")) {
        return;
      }
    }

    state.currentPageNum = pageNum;
    el.pageSelect.value = pageNum;
    el.btnPrevPage.disabled = pageNum <= 1;
    el.btnNextPage.disabled = pageNum >= total;

    await loadPageData(state.currentJobId, pageNum);
  }

  async function loadPageData(jobId, pageNum) {
    try {
      const res = await fetch(`/api/jobs/${jobId}/pages/${pageNum}/data`);
      if (!res.ok) return;
      const pageData = await res.json();
      state.currentPageData = pageData;
      state.currentRevision = pageData.revision || 1;
      state.hasUnsavedChanges = false;

      // 1. Load Reference Image
      el.refImage.src = pageData.reference_image.url;
      el.refImage.onload = () => {
        renderBoundingBoxes(pageData);
      };

      // 2. Load Final & Raw Text
      el.editorFinalText.value = pageData.final_text || "";
      el.viewerRawText.value = pageData.raw_text || "";
      el.revisionBadge.textContent = `Rev ${state.currentRevision}`;
      updateSaveIndicator("saved");

      // 3. Review Status
      updateReviewStatusBadge(pageData.review_status);

      // 4. Load AI Proposals & Character Diff
      renderProposalsAndDiff(pageData);

    } catch (err) {
      console.error("Load page data error:", err);
    }
  }

  function setZoom(newZoom) {
    const clamped = Math.max(0.4, Math.min(newZoom, 3.0));
    state.zoomLevel = clamped;
    el.imageViewport.style.transform = `scale(${clamped})`;
  }

  // Render SVG Bounding Boxes over Reference Image
  function renderBoundingBoxes(pageData) {
    el.bboxOverlay.innerHTML = "";
    const imgW = pageData.reference_image.width;
    const imgH = pageData.reference_image.height;

    el.bboxOverlay.setAttribute("viewBox", `0 0 ${imgW} ${imgH}`);

    const blocks = pageData.blocks || [];
    let boxIndex = 0;

    blocks.forEach((block) => {
      const lines = block.lines || [];
      lines.forEach((line) => {
        const bbox = line.bbox;
        if (!bbox) return;

        const currentIdx = boxIndex++;
        const rectEl = document.createElementNS("http://www.w3.org/2000/svg", "polygon");

        // Coordinates: x1,y1 to x4,y4
        const points = `${bbox.x1},${bbox.y1} ${bbox.x2},${bbox.y2} ${bbox.x3},${bbox.y3} ${bbox.x4},${bbox.y4}`;
        rectEl.setAttribute("points", points);
        rectEl.setAttribute("class", "bbox-rect");
        rectEl.setAttribute("data-box-index", currentIdx);
        rectEl.setAttribute("data-text", line.text || "");

        // Hover & Click Interaction
        rectEl.addEventListener("click", () => {
          highlightBoundingBox(currentIdx, line.text);
        });

        el.bboxOverlay.appendChild(rectEl);
      });
    });
  }

  function highlightBoundingBox(idx, text) {
    // Highlight SVG rect
    document.querySelectorAll(".bbox-rect").forEach(r => r.classList.remove("active"));
    const target = document.querySelector(`.bbox-rect[data-box-index="${idx}"]`);
    if (target) target.classList.add("active");

    // Scroll to text in editor
    if (text && el.editorFinalText.value.includes(text)) {
      const pos = el.editorFinalText.value.indexOf(text);
      el.editorFinalText.focus();
      el.editorFinalText.setSelectionRange(pos, pos + text.length);
    }
  }

  /* ==========================================================================
     Tabs & AI Proposals
     ========================================================================== */

  function activateTab(tabName) {
    [el.tabFinal, el.tabDiff, el.tabRaw].forEach(t => t.classList.remove("active"));
    [el.panelFinal, el.panelDiff, el.panelRaw].forEach(p => p.classList.add("hidden"));

    if (tabName === "final") {
      el.tabFinal.classList.add("active");
      el.panelFinal.classList.remove("hidden");
    } else if (tabName === "diff") {
      el.tabDiff.classList.add("active");
      el.panelDiff.classList.remove("hidden");
    } else if (tabName === "raw") {
      el.tabRaw.classList.add("active");
      el.panelRaw.classList.remove("hidden");
    }
  }

  function renderProposalsAndDiff(pageData) {
    const diff = pageData.diff_summary || {};
    el.metricLevenshtein.textContent = diff.levenshtein_distance || 0;
    el.metricSubstitutions.textContent = diff.substitutions || 0;
    el.metricInsertions.textContent = diff.insertions || 0;
    el.metricDeletions.textContent = diff.deletions || 0;

    const corrections = pageData.changes || [];
    el.badgeProposalsCount.textContent = corrections.length;

    el.proposalsList.innerHTML = "";

    if (corrections.length === 0) {
      el.proposalsList.innerHTML = '<div class="empty-placeholder">ไม่มีข้อเสนอการแก้ไขในหน้านี้ (AI ยืนยันข้อความตรงตามต้นฉบับ)</div>';
      return;
    }

    corrections.forEach((c) => {
      const card = document.createElement("div");
      card.className = "proposal-card";
      card.id = `proposal-card-${c.change_id}`;

      const catName = formatCategory(c.category);
      const isNamed = c.is_named_entity_or_number ? '<span class="badge badge-warning">ต้องตรวจทาน (ตัวเลข/ชื่อ)</span>' : '';
      const statusBadge = `<span class="badge badge-${c.status === 'accepted' ? 'success' : c.status === 'rejected' ? 'danger' : 'neutral'}">${c.status}</span>`;

      card.innerHTML = `
        <div class="proposal-header">
          <div class="proposal-badges">
            <span class="badge badge-info">${catName}</span>
            ${isNamed}
            ${statusBadge}
          </div>
          <span class="text-xs text-muted font-mono">${c.change_id}</span>
        </div>
        <div class="proposal-diff-view">
          <span class="diff-orig">${escapeHtml(c.original_text)}</span>
          <span class="diff-arrow">→</span>
          <span class="diff-corr">${escapeHtml(c.corrected_text)}</span>
        </div>
        <div class="proposal-actions">
          <button class="btn btn-outline btn-success btn-xs btn-accept" data-id="${c.change_id}">
            ยอมรับ
          </button>
          <button class="btn btn-outline btn-danger btn-xs btn-revert" data-id="${c.change_id}">
            คืนค่า
          </button>
        </div>
      `;

      card.querySelector(".btn-accept").addEventListener("click", () => acceptCorrection(c.change_id));
      card.querySelector(".btn-revert").addEventListener("click", () => revertCorrection(c.change_id));

      el.proposalsList.appendChild(card);
    });
  }

  function formatCategory(cat) {
    switch (cat) {
      case "spelling": return "การสะกดคำ";
      case "vowel_tone": return "สระ/วรรณยุกต์";
      case "number": return "ตัวเลข";
      case "named_entity": return "ชื่อเฉพาะ";
      default: return "ทั่วไป";
    }
  }

  function escapeHtml(str) {
    if (!str) return "";
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  /* ==========================================================================
     Proposal Accept / Revert Actions
     ========================================================================== */

  async function acceptCorrection(changeId) {
    try {
      const res = await fetch(`/api/jobs/${state.currentJobId}/pages/${state.currentPageNum}/corrections/${changeId}/accept`, {
        method: "POST",
      });
      if (!res.ok) throw new Error("Accept proposal failed");
      await loadPageData(state.currentJobId, state.currentPageNum);
    } catch (err) {
      alert(`ยอมรับข้อเสนอไม่สำเร็จ: ${err.message}`);
    }
  }

  async function revertCorrection(changeId) {
    try {
      const res = await fetch(`/api/jobs/${state.currentJobId}/pages/${state.currentPageNum}/corrections/${changeId}/revert`, {
        method: "POST",
      });
      if (!res.ok) throw new Error("Revert proposal failed");
      await loadPageData(state.currentJobId, state.currentPageNum);
    } catch (err) {
      alert(`คืนค่าไม่สำเร็จ: ${err.message}`);
    }
  }

  async function acceptAllCorrections() {
    try {
      const res = await fetch(`/api/jobs/${state.currentJobId}/pages/${state.currentPageNum}/corrections/accept-all`, {
        method: "POST",
      });
      if (!res.ok) throw new Error("Accept all failed");
      await loadPageData(state.currentJobId, state.currentPageNum);
    } catch (err) {
      alert(`ยอมรับทั้งหมดไม่สำเร็จ: ${err.message}`);
    }
  }

  async function revertAllCorrections() {
    try {
      const res = await fetch(`/api/jobs/${state.currentJobId}/pages/${state.currentPageNum}/corrections/revert-all`, {
        method: "POST",
      });
      if (!res.ok) throw new Error("Revert all failed");
      await loadPageData(state.currentJobId, state.currentPageNum);
    } catch (err) {
      alert(`คืนค่าทั้งหมดไม่สำเร็จ: ${err.message}`);
    }
  }

  /* ==========================================================================
     Manual Text Editing & Revision Conflict Detection
     ========================================================================== */

  async function saveManualEdit() {
    if (!state.currentJobId || !state.currentPageNum) return;

    updateSaveIndicator("saving");
    const editedText = el.editorFinalText.value;

    try {
      const res = await fetch(`/api/jobs/${state.currentJobId}/pages/${state.currentPageNum}/edit`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_revision: state.currentRevision,
          edited_text: editedText,
          check_conflict: true,
        }),
      });

      if (res.status === 409) {
        // Revision Conflict detected! Never silently overwrite.
        const conflictData = await res.json();
        showConflictModal(conflictData.detail, editedText);
        updateSaveIndicator("unsaved");
        return;
      }

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Save edit failed");
      }

      const saveRes = await res.json();
      state.currentRevision = saveRes.new_revision;
      state.hasUnsavedChanges = false;
      el.revisionBadge.textContent = `Rev ${state.currentRevision}`;
      updateSaveIndicator("saved");

      // Transition review status in UI
      updateReviewStatusBadge("in_review");

    } catch (err) {
      alert(`บันทึกไม่สำเร็จ: ${err.message}`);
      updateSaveIndicator("unsaved");
    }
  }

  function showConflictModal(detail, unsaved) {
    el.modalConflictText.textContent = detail || "หน้านี้มีการแก้ไขใหม่จากแท็บอื่นแล้ว เพื่อป้องกันข้อมูลสูญหาย กรุณาคัดลอกข้อความไว้หรือโหลดฉบับล่าสุด";
    el.conflictUnsavedText.value = unsaved;
    el.modalConflict.classList.remove("hidden");
  }

  function updateSaveIndicator(status) {
    el.saveIndicator.className = `save-indicator ${status}`;
    if (status === "saved") el.saveStatusText.textContent = "บันทึกแล้ว";
    else if (status === "unsaved") el.saveStatusText.textContent = "มีการแก้ไขที่ยังไม่บันทึก";
    else if (status === "saving") el.saveStatusText.textContent = "กำลังบันทึก...";
  }

  /* ==========================================================================
     Review Status & Finalization
     ========================================================================== */

  function updateReviewStatusBadge(st) {
    el.badgePageReviewStatus.textContent = st === "reviewed" ? "ตรวจทานเสร็จสมบูรณ์" : st === "in_review" ? "กำลังตรวจทาน" : "ยังไม่ตรวจทาน";
    el.badgePageReviewStatus.className = `badge badge-${st === "reviewed" ? "reviewed" : st === "in_review" ? "in-review" : "unreviewed"}`;

    if (st === "reviewed") {
      el.btnMarkReviewed.classList.add("btn-outline");
      el.btnMarkReviewed.innerHTML = "<span>ตรวจทานแล้ว ✓</span>";
    } else {
      el.btnMarkReviewed.classList.remove("btn-outline");
      el.btnMarkReviewed.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg><span>ยืนยันตรวจทานครบถ้วน</span>';
    }
  }

  async function markAsReviewed() {
    if (!state.currentJobId) return;

    try {
      const res = await fetch(`/api/jobs/${state.currentJobId}/review?new_status=reviewed`, {
        method: "POST",
      });
      if (!res.ok) throw new Error("Failed to update review status");
      updateReviewStatusBadge("reviewed");
    } catch (err) {
      alert(`ยืนยันสถานะไม่สำเร็จ: ${err.message}`);
    }
  }

  /* ==========================================================================
     Downloads & Export Warnings
     ========================================================================== */

  function updateDownloadLinks(job) {
    const jId = job.job_id;
    el.btnDownloadRaw.href = `/api/jobs/${jId}/download/raw.txt`;
    el.btnDownloadCorrected.href = `/api/jobs/${jId}/download/corrected.txt`;
    el.btnDownloadFinal.href = `/api/jobs/${jId}/download/final.txt`;
    el.btnDownloadBundle.href = `/api/jobs/${jId}/download/bundle.zip`;
    el.btnDownloadCorrected.classList.toggle("hidden", !job.enable_ai);

    // Warning banner if failed or partial
    const hasFailures = job.failed_pages > 0 || job.status === "partial" || job.status === "failed" || job.status === "cancelled";
    if (hasFailures) {
      el.downloadWarningBanner.classList.remove("hidden");
    } else {
      el.downloadWarningBanner.classList.add("hidden");
    }
  }

  // Start app
  document.addEventListener("DOMContentLoaded", init);
})();
