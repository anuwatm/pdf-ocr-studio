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
    selectedPageIds: [],
    previewedCompletedPageIds: [],
    currentPageData: null,
    currentRevision: 1,
    hasUnsavedChanges: false,
    unsavedText: "",
    zoomLevel: 1.0,
    aiConnected: false,
    pollTimer: null,
    activeBoxIndex: null,
    activeMainTab: "upload",
    htmlBaseRevision: 1,
    currentHtmlVariant: "basic",
    activeHtmlSubtab: "preview",
    epubPreviewRevision: null,
    activeEpubSubtab: "preview",
    postOcrDestination: null,
  };

  // DOM Elements
  const el = {
    themeToggle: document.getElementById("btn-theme-toggle"),
    aiStatusBadge: document.getElementById("ai-status-badge"),
    aiStatusText: document.getElementById("ai-status-text"),
    btnTestAiConnection: document.getElementById("btn-test-ai-connection"),
    aiAvailableBadge: document.getElementById("ai-available-badge"),
    modeOcrAi: document.getElementById("mode-ocr-ai"),
    modeOcrOnly: document.getElementById("mode-ocr-only"),
    includePageNumbers: document.getElementById("include-page-numbers"),
    mainTabButtons: [...document.querySelectorAll("[data-main-tab]")],
    mainTabPanels: [...document.querySelectorAll("[data-main-panel]")],
    tabProgressEmpty: document.getElementById("tab-progress-empty"),

    // Upload
    dropzone: document.getElementById("dropzone"),
    fileInput: document.getElementById("file-input"),
    fileSelectedBox: document.getElementById("file-selected-box"),
    selectedFileName: document.getElementById("selected-file-name"),
    selectedFileSize: document.getElementById("selected-file-size"),
    selectedFileIcon: document.getElementById("selected-file-icon"),
    btnRemoveFile: document.getElementById("btn-remove-file"),
    btnStartJob: document.getElementById("btn-start-job"),
    btnStartJobHtml: document.getElementById("btn-start-job-html"),
    btnEditStructuredHtml: document.getElementById("btn-edit-structured-html"),
    pageOptions: document.getElementById("page-options"),
    pdfPageSummary: document.getElementById("pdf-page-summary"),
    inputPageStart: document.getElementById("input-page-start"),
    inputPageEnd: document.getElementById("input-page-end"),
    pageRangeLimit: document.getElementById("page-range-limit"),

    // Previous jobs
    historyList: document.getElementById("history-list"),
    historyMessage: document.getElementById("history-message"),
    btnRefreshHistory: document.getElementById("btn-refresh-history"),
    inputRetentionDays: document.getElementById("input-retention-days"),
    btnCleanupHistory: document.getElementById("btn-cleanup-history"),
    btnDeleteAllHistory: document.getElementById("btn-delete-all-history"),

    // Progress Section
    sectionProgress: document.getElementById("section-progress"),
    jobIdBadge: document.getElementById("job-id-badge"),
    jobStatusBadge: document.getElementById("job-status-badge"),
    jobAttemptBadge: document.getElementById("job-attempt-badge"),
    progressBarFill: document.getElementById("progress-bar-fill"),
    progressTextPages: document.getElementById("progress-text-pages"),
    progressTextPercent: document.getElementById("progress-text-percent"),
    currentProcessingPage: document.getElementById("current-processing-page"),
    btnCancelJob: document.getElementById("btn-cancel-job"),
    btnRetryJob: document.getElementById("btn-retry-job"),
    btnFullTextAi: document.getElementById("btn-full-text-ai"),
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
    tabHtml: document.getElementById("tab-html"),
    tabEpub: document.getElementById("tab-epub"),
    panelFinal: document.getElementById("panel-final"),
    panelDiff: document.getElementById("panel-diff"),
    panelRaw: document.getElementById("panel-raw"),
    panelHtml: document.getElementById("panel-html"),
    panelEpub: document.getElementById("panel-epub"),
    badgeProposalsCount: document.getElementById("badge-proposals-count"),

    // Phase 7: Structured HTML Export & Sandboxed Preview
    btnGenerateHtmlBasic: document.getElementById("btn-generate-html-basic"),
    btnGenerateHtmlAi: document.getElementById("btn-generate-html-ai"),
    htmlExportStatusBadge: document.getElementById("html-export-status-badge"),
    btnSubtabPreview: document.getElementById("btn-subtab-preview"),
    btnSubtabSource: document.getElementById("btn-subtab-source"),
    htmlPreviewView: document.getElementById("html-preview-view"),
    htmlPreviewFrame: document.getElementById("html-preview-frame"),
    htmlSourceView: document.getElementById("html-source-view"),
    htmlSourceEditor: document.getElementById("html-source-editor"),
    htmlSourceStatusText: document.getElementById("html-source-status-text"),
    btnSaveFinalHtml: document.getElementById("btn-save-final-html"),
    btnDlHtmlBasic: document.getElementById("btn-dl-html-basic"),
    btnDlHtmlAi: document.getElementById("btn-dl-html-ai"),
    btnDlHtmlFinal: document.getElementById("btn-dl-html-final"),

    // Phase 8: EPUB Export & XHTML Quick Preview
    epubSourceVariant: document.getElementById("epub-source-variant"),
    epubChapterSplit: document.getElementById("epub-chapter-split"),
    epubTitle: document.getElementById("epub-title"),
    epubCreator: document.getElementById("epub-creator"),
    epubPublisher: document.getElementById("epub-publisher"),
    epubLanguage: document.getElementById("epub-language"),
    btnGenerateEpubPreview: document.getElementById("btn-generate-epub-preview"),
    btnBuildEpub: document.getElementById("btn-build-epub"),
    epubExportStatusBadge: document.getElementById("epub-export-status-badge"),
    btnEpubSubtabPreview: document.getElementById("btn-epub-subtab-preview"),
    btnEpubSubtabSource: document.getElementById("btn-epub-subtab-source"),
    epubPreviewView: document.getElementById("epub-preview-view"),
    epubPreviewFrame: document.getElementById("epub-preview-frame"),
    epubSourceView: document.getElementById("epub-source-view"),
    epubSourceEditor: document.getElementById("epub-source-editor"),
    btnDlEpub: document.getElementById("btn-dl-epub"),

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
    btnDownloadHtml: document.getElementById("btn-download-html"),
    btnDownloadEpub: document.getElementById("btn-download-epub"),
    btnDownloadPageImages: document.getElementById("btn-download-page-images"),

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

  const {activateTab, renderProposalsAndDiff, acceptAllCorrections, revertAllCorrections, saveManualEdit, updateSaveIndicator, updateReviewStatusBadge, markAsReviewed} = createTextWorkspace({state, el, loadPageData});
  const {switchEpubSubtab, loadEpubExportStatus, generateEpubPreview, buildEpubPackage} = createEpubWorkspace({state, el});
  const structuredWorkspace = createStructuredWorkspace({state, el});
  const htmlWorkspace = createHtmlWorkspace({state, el, loadEpubExportStatus});
  const {switchHtmlSubtab, loadHtmlExportStatus, generateHtmlExport, saveFinalHtml} = htmlWorkspace;

  function init() {
    setupTheme();
    htmlWorkspace.init();
    structuredWorkspace.init();
    setupDropzone();
    setupEventListeners();
    activateMainTab("upload");
    checkAiStatus();
    loadJobHistory();
    const pendingHtmlAiJob = sessionStorage.getItem("htmlAiJobId");
    if (pendingHtmlAiJob) {
      openPreviousJob(pendingHtmlAiJob).then(() => {
        if (state.currentJobId === pendingHtmlAiJob) activateMainTab("html");
        else sessionStorage.removeItem("htmlAiJobId");
      });
    }
    setInterval(checkAiStatus, 10000);
  }

  // Theme Management
  function setupTheme() {
    const savedTheme = localStorage.getItem("theme") || "theme-light";
    document.body.className = savedTheme;

    el.themeToggle.addEventListener("click", () => {
      const isDark = document.body.classList.contains("theme-dark");
      const newTheme = isDark ? "theme-light" : "theme-dark";
      document.body.className = newTheme;
      localStorage.setItem("theme", newTheme);
    });
  }

  // Check Local LLM Status
  function setAiModeAvailability(isAvailable) {
    el.modeOcrAi.disabled = !isAvailable;
    el.modeOcrAi.closest(".option-card")?.classList.toggle("option-disabled", !isAvailable);
    if (!isAvailable) el.modeOcrOnly.checked = true;
  }

  async function checkAiStatus() {
    try {
      const res = await fetch("/api/ai/status");
      if (!res.ok) throw new Error("AI service unavailable");
      const data = await res.json();

      if (data.status === "connected") {
        state.aiConnected = true;
        setAiModeAvailability(true);
        el.aiStatusBadge.className = "status-badge status-online";
        el.aiStatusText.textContent = `Online: ${data.configured_model}`;
        el.aiAvailableBadge.className = "badge badge-success";
        el.aiAvailableBadge.textContent = "พร้อมใช้งาน";
      } else {
        state.aiConnected = false;
        setAiModeAvailability(false);
        el.aiStatusBadge.className = "status-badge status-offline";
        el.aiStatusText.textContent = "Offline (Local AI ไม่พร้อม)";
        el.aiAvailableBadge.className = "badge badge-warning";
        el.aiAvailableBadge.textContent = "ออฟไลน์";
      }
    } catch {
      state.aiConnected = false;
      setAiModeAvailability(false);
      el.aiStatusBadge.className = "status-badge status-offline";
      el.aiStatusText.textContent = "Offline: Local AI 127.0.0.1:1234";
      el.aiAvailableBadge.className = "badge badge-warning";
      el.aiAvailableBadge.textContent = "ออฟไลน์";
    }
  }

  async function testAiConnection() {
    el.btnTestAiConnection.disabled = true;
    el.btnTestAiConnection.textContent = "กำลังทดสอบ...";
    await checkAiStatus();
    el.btnTestAiConnection.disabled = false;
    el.btnTestAiConnection.textContent = state.aiConnected ? "เชื่อมต่อแล้ว" : "ทดสอบอีกครั้ง";
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

    if (file.size > 300 * 1024 * 1024) {
      alert("ไฟล์มีขนาดเกินเพดาน 300 MB กรุณาเลือกไฟล์ที่มีขนาดไม่เกิน 300 MB");
      return;
    }

    state.selectedFile = file;
    state.uploadedJob = null;
    el.btnDownloadPageImages.disabled = true;
    delete el.btnDownloadPageImages.dataset.downloadUrl;
    el.selectedFileName.textContent = file.name;
    el.selectedFileSize.textContent = formatBytes(file.size);
    el.selectedFileIcon.textContent = ext.replace(".", "").toUpperCase();

    el.dropzone.classList.add("hidden");
    el.fileSelectedBox.classList.remove("hidden");
    el.btnStartJob.disabled = false;
    el.btnStartJob.innerHTML = "<span>ตรวจสอบจำนวนหน้า</span>";
    el.btnStartJobHtml?.classList.add("hidden");
    if (el.btnStartJobHtml) el.btnStartJobHtml.disabled = true;
    el.pageOptions.classList.add("hidden");

    // PDF page count is needed before the user can choose a range, so upload
    // and inspect it immediately after selection rather than waiting for a click.
    if (ext === ".pdf") {
      uploadSelectedFileAndPrepare().catch(err => {
        alert(`ตรวจสอบ PDF ไม่สำเร็จ: ${err.message}`);
        el.btnStartJob.disabled = false;
        el.btnStartJob.innerHTML = "<span>ตรวจสอบจำนวนหน้า</span>";
      });
    }
  }

  function resetFileSelection() {
    state.selectedFile = null;
    state.uploadedJob = null;
    el.btnDownloadPageImages.disabled = true;
    delete el.btnDownloadPageImages.dataset.downloadUrl;
    state.previewedCompletedPageIds = [];
    state.currentPageData = null;
    el.fileInput.value = "";
    el.fileSelectedBox.classList.add("hidden");
    el.dropzone.classList.remove("hidden");
    el.btnStartJob.disabled = true;
    el.btnStartJob.innerHTML = "<span>ตรวจสอบจำนวนหน้า</span>";
    el.btnStartJobHtml?.classList.add("hidden");
    if (el.btnStartJobHtml) el.btnStartJobHtml.disabled = true;
    el.pageOptions.classList.add("hidden");
  }

  function formatBytes(bytes) {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
  }

  async function uploadSelectedFileAndPrepare() {
    if (!state.selectedFile || state.uploadedJob) return;
    el.btnStartJob.disabled = true;
    el.btnStartJob.innerHTML = "<span>กำลังตรวจสอบจำนวนหน้า...</span>";
    if (el.btnStartJobHtml) el.btnStartJobHtml.disabled = true;

    const formData = new FormData();
    formData.append("file", state.selectedFile);
    const upRes = await fetch("/api/upload", { method: "POST", body: formData });
    if (!upRes.ok) {
      const err = await upRes.json();
      throw new Error(err.detail || "Upload failed");
    }

    state.uploadedJob = await upRes.json();
    if (!el.inputPageStart || !el.inputPageEnd || !el.pageRangeLimit) {
      throw new Error("หน้าเว็บเป็นเวอร์ชันเก่า กรุณากด Ctrl+F5 เพื่อโหลดหน้าเลือกช่วงหน้าใหม่");
    }
    const sourcePages = state.uploadedJob.total_pages;
    const endPage = sourcePages;
    const totalBatches = Math.ceil(sourcePages / 200);
    el.pdfPageSummary.textContent = `เอกสารนี้มี ${sourcePages} หน้า`;
    el.inputPageStart.min = "1";
    el.inputPageStart.max = String(sourcePages);
    el.inputPageStart.value = "1";
    el.inputPageEnd.min = "1";
    el.inputPageEnd.max = String(sourcePages);
    el.inputPageEnd.value = String(endPage);
    el.inputPageStart.disabled = false;
    el.inputPageEnd.disabled = false;
    el.pageRangeLimit.textContent = `เลือก ${endPage} หน้า • ระบบแบ่ง ${totalBatches} batch ละ 200 หน้า`;
    el.pageOptions.classList.remove("hidden");
    el.btnStartJob.disabled = false;
    el.btnStartJobHtml?.classList.remove("hidden");
    updateRangeButton();
  }

  /* ==========================================================================
     Job Start & Progress Polling
     ========================================================================== */

  function setupEventListeners() {
    el.mainTabButtons.forEach(button => {
      button.addEventListener("click", () => activateMainTab(button.dataset.mainTab));
    });
    el.btnStartJob.addEventListener("click", () => startJobFlow("text"));
    el.btnStartJobHtml?.addEventListener("click", () => startJobFlow("html"));
    el.btnEditStructuredHtml?.addEventListener("click", async () => {
      activateMainTab("html");
      try {
        await htmlWorkspace.loadStructuredHtml();
      } catch (error) {
        alert(`เปิด Structured HTML ไม่สำเร็จ: ${error.message}`);
      }
    });
    el.btnDownloadPageImages.addEventListener("click", () => {
      if (!el.btnDownloadPageImages.disabled && el.btnDownloadPageImages.dataset.downloadUrl) {
        window.location.assign(el.btnDownloadPageImages.dataset.downloadUrl);
      }
    });
    el.btnRefreshHistory.addEventListener("click", loadJobHistory);
    el.btnCleanupHistory.addEventListener("click", cleanupOldJobs);
    el.btnDeleteAllHistory.addEventListener("click", deleteAllJobs);
    el.btnTestAiConnection.addEventListener("click", testAiConnection);
    [el.inputPageStart, el.inputPageEnd]
      .filter(Boolean)
      .forEach(input => input.addEventListener("input", updateRangeButton));
    el.btnCancelJob.addEventListener("click", cancelCurrentJob);
    el.btnFullTextAi.addEventListener("click", () => retryCurrentJob("full_text_ai"));

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
    el.btnPrevPage.addEventListener("click", () => switchPageByOffset(-1));
    el.btnNextPage.addEventListener("click", () => switchPageByOffset(1));
    el.pageSelect.addEventListener("change", (e) => switchPage(parseInt(e.target.value, 10)));

    // Zoom controls
    el.btnZoomIn.addEventListener("click", () => setZoom(state.zoomLevel + 0.15));
    el.btnZoomOut.addEventListener("click", () => setZoom(state.zoomLevel - 0.15));
    el.btnZoomReset.addEventListener("click", () => setZoom(1.0));

    // Tabs
    el.tabFinal.addEventListener("click", () => activateTab("final"));
    el.tabDiff.addEventListener("click", () => activateTab("diff"));
    el.tabRaw.addEventListener("click", () => activateTab("raw"));
    el.tabHtml?.addEventListener("click", () => activateTab("html"));
    el.tabEpub?.addEventListener("click", () => activateTab("epub"));

    // Phase 7 HTML Export Actions
    el.btnGenerateHtmlBasic?.addEventListener("click", () => generateHtmlExport("basic"));
    el.btnGenerateHtmlAi?.addEventListener("click", () => generateHtmlExport("ai"));
    el.btnSubtabPreview?.addEventListener("click", () => switchHtmlSubtab("preview"));
    el.btnSubtabSource?.addEventListener("click", () => switchHtmlSubtab("source"));
    el.btnSaveFinalHtml?.addEventListener("click", saveFinalHtml);

    // Phase 8 EPUB Export Actions
    el.btnGenerateEpubPreview?.addEventListener("click", generateEpubPreview);
    el.btnBuildEpub?.addEventListener("click", buildEpubPackage);
    el.btnEpubSubtabPreview?.addEventListener("click", () => switchEpubSubtab("preview"));
    el.btnEpubSubtabSource?.addEventListener("click", () => switchEpubSubtab("source"));
    [el.epubSourceVariant, el.epubChapterSplit, el.epubTitle, el.epubCreator, el.epubPublisher, el.epubLanguage]
      .filter(Boolean)
      .forEach(input => input.addEventListener("input", () => {
        state.epubConfigDirty = true;
        state.epubPreviewRevision = null;
        if (el.btnBuildEpub) el.btnBuildEpub.disabled = true;
        if (el.epubExportStatusBadge) {
          el.epubExportStatusBadge.textContent = "ตั้งค่าเปลี่ยน — สร้าง Preview ใหม่";
          el.epubExportStatusBadge.className = "badge badge-warning";
        }
      }));

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
        if (state.activeMainTab === "html") saveFinalHtml();
        else if (state.activeMainTab === "progress") saveManualEdit();
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

  function activateMainTab(tabName) {
    const validTabs = new Set(["upload", "progress", "html", "epub", "structured", "history"]);
    if (!validTabs.has(tabName)) return;

    state.activeMainTab = tabName;
    el.mainTabButtons.forEach(button => {
      const isActive = button.dataset.mainTab === tabName;
      button.classList.toggle("active", isActive);
      button.setAttribute("aria-selected", String(isActive));
    });
    el.mainTabPanels.forEach(panel => {
      panel.classList.toggle("main-tab-hidden", panel.dataset.mainPanel !== tabName);
    });

    refreshExportContext();
    if (tabName === "html") {
      htmlWorkspace.refresh();
      loadHtmlExportStatus();
    }
    if (tabName === "epub") loadEpubExportStatus();
    if (tabName === "structured") structuredWorkspace.loadStatus();
    const hasJob = Boolean(state.currentJobId);
    el.tabProgressEmpty.classList.toggle("hidden", tabName !== "progress" || hasJob);
    if (tabName === "history") loadJobHistory();
  }

  async function startJobFlow(destination = "text") {
    if (!state.selectedFile) return;

    state.postOcrDestination = destination;
    el.btnStartJob.disabled = true;
    if (el.btnStartJobHtml) el.btnStartJobHtml.disabled = true;

    try {
      if (!state.uploadedJob) {
        await uploadSelectedFileAndPrepare();
        return;
      }

      if (state.jobStatus?.status === "cancelled" && state.currentJobId === state.uploadedJob.job_id) {
        await retryCurrentJob("failed_only");
        return;
      }

      const pageStart = Number.parseInt(el.inputPageStart.value, 10);
      const pageEnd = Number.parseInt(el.inputPageEnd.value, 10);
      const selectedPages = pageEnd - pageStart + 1;
      if (!Number.isInteger(pageStart) || !Number.isInteger(pageEnd) || pageStart < 1 || pageEnd < pageStart || pageEnd > state.uploadedJob.total_pages) {
        throw new Error("กรุณาเลือกช่วงหน้าที่ถูกต้อง");
      }

      const activeButton = destination === "html" ? el.btnStartJobHtml : el.btnStartJob;
      if (activeButton) activeButton.innerHTML = `<span>กำลังเริ่ม OCR เพื่อ ${destination === "html" ? "HTML" : "Text"}...</span>`;
      const enableAi = el.modeOcrAi.checked;
      if (!htmlWorkspace.confirmJobChange(state.uploadedJob.job_id)) {
        updateRangeButton();
        return;
      }
      state.currentJobId = state.uploadedJob.job_id;
      state.previewedCompletedPageIds = [];
      state.currentPageData = null;
      const startRes = await fetch(`/api/jobs/${state.currentJobId}/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enable_ai: enableAi, page_start: pageStart, page_end: pageEnd, include_page_numbers: el.includePageNumbers.checked }),
      });
      if (!startRes.ok) {
        const err = await startRes.json();
        throw new Error(err.detail || "Failed to start job");
      }
      const startedJob = await startRes.json();
      if (startedJob.page_start !== pageStart || startedJob.page_end !== pageEnd) {
        // An already-running server can retain an older API that ignores the
        // selected range. Stop it before it OCRs the wrong pages.
        await fetch(`/api/jobs/${state.currentJobId}/cancel`, { method: "POST" });
        throw new Error("server ยังเป็นเวอร์ชันเก่า กรุณาปิดแล้วเปิด run_server.cmd ใหม่ แล้วลองอีกครั้ง");
      }

      // 3. Show Progress & Workspace
      el.sectionProgress.classList.remove("hidden");
      activateMainTab("progress");
      el.jobIdBadge.textContent = state.currentJobId;
      startStatusPolling();
    } catch (err) {
      alert(`เกิดข้อผิดพลาด: ${err.message}`);
      state.postOcrDestination = null;
      if (state.uploadedJob) updateRangeButton();
      else {
        el.btnStartJob.disabled = false;
        el.btnStartJob.innerHTML = "<span>ตรวจสอบจำนวนหน้า</span>";
      }
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

      const pageIds = job.pages.map(page => page.page_id);
      if (pageIds.join(",") !== state.selectedPageIds.join(",")) {
        state.selectedPageIds = pageIds;
        updatePageSelector(job.pages);
      }

      previewNewlyCompletedPage(job);

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
        loadJobHistory();
        const destination = state.postOcrDestination;
        state.postOcrDestination = null;
        if (destination === "html" && ["completed", "partial"].includes(job.status) && job.completed_pages > 0) {
          activateMainTab("structured");
          await structuredWorkspace.generate();
        }
        if (job.status === "cancelled" && state.uploadedJob?.job_id === job.job_id) {
          updateRangeButton();
        }
      }
    } catch (err) {
      console.error("Status poll error:", err);
    }
  }

  function previewNewlyCompletedPage(job) {
    const completedIds = job.pages
      .filter(page => page.status === "completed" || page.status === "blank")
      .map(page => page.page_id);
    const newlyCompletedIds = completedIds.filter(pageId => !state.previewedCompletedPageIds.includes(pageId));
    if (newlyCompletedIds.length === 0) return;

    state.previewedCompletedPageIds.push(...newlyCompletedIds);
    if (state.hasUnsavedChanges) return;

    const latestPageId = newlyCompletedIds[newlyCompletedIds.length - 1];
    el.sectionWorkspace.classList.remove("hidden");
    switchPage(latestPageId);
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
    const runningPage = job.pages.find(page => page.status === "running");
    const batchText = job.total_batches > 1 ? `Batch ${job.current_batch}/${job.total_batches} • ` : "";
    el.currentProcessingPage.textContent = runningPage
      ? `${batchText}กำลัง OCR หน้า ${runningPage.page_num}`
      : job.status === "queued" ? `${batchText}รอคิวประมวลผล` : `${batchText}ประมวลผลแล้ว ${completed} หน้า`;

    // Action buttons
    if (job.status === "queued" || job.status === "running") {
      el.btnCancelJob.classList.remove("hidden");
      el.btnRetryJob.classList.add("hidden");
      el.btnFullTextAi.classList.add("hidden");
    } else {
      el.btnCancelJob.classList.add("hidden");
      el.btnRetryJob.classList.remove("hidden");
      el.btnFullTextAi.classList.toggle("hidden", !state.aiConnected);
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
      el.btnCancelJob.disabled = true;
      const res = await fetch(`/api/jobs/${state.currentJobId}/cancel`, { method: "POST" });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Cancel failed");
      }
      pollJobStatus();
    } catch (err) {
      alert(`ยกเลิกงานไม่สำเร็จ: ${err.message}`);
    } finally {
      el.btnCancelJob.disabled = false;
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

  /* ========================================================================
     Previous Jobs & Storage Cleanup
     ======================================================================== */

  function escapeHtml(value) {
    return String(value || "").replace(/[&<>'"]/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);
  }

  function formatHistoryDate(value) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? value : date.toLocaleString("th-TH");
  }

  function formatFileSize(bytes) {
    if (!Number.isFinite(bytes)) return "-";
    return bytes < 1024 * 1024 ? `${Math.ceil(bytes / 1024)} KB` : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  async function loadJobHistory() {
    try {
      const res = await fetch("/api/jobs?limit=100");
      if (!res.ok) throw new Error("โหลดประวัติงานไม่สำเร็จ");
      const jobs = await res.json();
      if (!jobs.length) {
        el.historyMessage.textContent = "ยังไม่มีงาน OCR ที่บันทึกไว้";
        el.historyList.innerHTML = "";
        return;
      }
      el.historyMessage.textContent = `พบ ${jobs.length} งานล่าสุด`;
      el.historyList.innerHTML = jobs.map(job => `
        <article class="history-row">
          <div class="history-job-info">
            <strong>${escapeHtml(job.filename)}</strong>
            <span>${escapeHtml(job.job_id)} · ${job.total_pages} หน้า · ${formatFileSize(job.file_size_bytes)}</span>
            <small>${formatHistoryDate(job.updated_at)}</small>
          </div>
          <span class="badge badge-${getStatusBadgeType(job.status)}">${escapeHtml(job.status)}</span>
          <div class="history-row-actions">
            <button class="btn btn-outline btn-xs" data-history-open="${escapeHtml(job.job_id)}" type="button">เปิดดู</button>
            <button class="btn btn-outline btn-danger btn-xs" data-history-delete="${escapeHtml(job.job_id)}" type="button">ลบ</button>
          </div>
        </article>`).join("");
      el.historyList.querySelectorAll("[data-history-open]").forEach(btn => btn.addEventListener("click", () => openPreviousJob(btn.dataset.historyOpen)));
      el.historyList.querySelectorAll("[data-history-delete]").forEach(btn => btn.addEventListener("click", () => deletePreviousJob(btn.dataset.historyDelete)));
    } catch (err) {
      el.historyMessage.textContent = `โหลดประวัติงานไม่สำเร็จ: ${err.message}`;
    }
  }

  async function openPreviousJob(jobId) {
    if (!htmlWorkspace.confirmJobChange(jobId)) return;
    try {
      const res = await fetch(`/api/jobs/${jobId}/status`);
      if (!res.ok) throw new Error("ไม่พบงานนี้");
      const job = await res.json();
      state.currentJobId = jobId;
      state.jobStatus = job;
      state.selectedPageIds = job.pages.map(page => page.page_id);
      state.previewedCompletedPageIds = [...state.selectedPageIds];
      state.currentPageNum = state.selectedPageIds[0] || 1;
      el.sectionProgress.classList.remove("hidden");
      el.sectionWorkspace.classList.remove("hidden");
      activateMainTab("progress");
      updateProgressUI(job);
      updatePageSelector(job.pages);
      updateDownloadLinks(job);
      await switchPage(state.currentPageNum);
      window.scrollTo({ top: el.sectionWorkspace.offsetTop - 16, behavior: "smooth" });
    } catch (err) {
      alert(`เปิดงานเก่าไม่สำเร็จ: ${err.message}`);
    }
  }

  async function deletePreviousJob(jobId) {
    if (!confirm("ลบไฟล์ต้นฉบับ ผล OCR และประวัติของงานนี้ถาวรหรือไม่?")) return;
    try {
      const res = await fetch(`/api/jobs/${jobId}`, { method: "DELETE" });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "ลบงานไม่สำเร็จ");
      }
      if (state.currentJobId === jobId) state.currentJobId = null;
      await loadJobHistory();
    } catch (err) {
      alert(`ลบงานไม่สำเร็จ: ${err.message}`);
    }
  }

  async function cleanupOldJobs() {
    const days = Number.parseInt(el.inputRetentionDays.value, 10);
    if (!Number.isInteger(days) || days < 1) {
      alert("กรุณาระบุจำนวนวันตั้งแต่ 1 วันขึ้นไป");
      return;
    }
    if (!confirm(`ลบงานที่เสร็จแล้วและเก่ากว่า ${days} วันถาวรหรือไม่? งานที่กำลังทำจะไม่ถูกลบ`)) return;
    try {
      const res = await fetch(`/api/admin/cleanup?max_age_seconds=${days * 86400}`, { method: "POST" });
      if (!res.ok) throw new Error("ลบงานเก่าไม่สำเร็จ");
      const data = await res.json();
      await loadJobHistory();
      el.historyMessage.textContent = `ลบงานเก่าแล้ว ${data.cleaned_count} งาน${data.skipped_active_jobs.length ? ` · ข้ามงานที่กำลังทำ ${data.skipped_active_jobs.length} งาน` : ""}`;
    } catch (err) {
      alert(`ลบงานเก่าไม่สำเร็จ: ${err.message}`);
    }
  }

  async function deleteAllJobs() {
    if (!confirm("ลบงานทั้งหมดถาวรหรือไม่? รวมไฟล์ต้นฉบับ ผล OCR และประวัติของทุกงาน งานรอคิวและงานกำลังประมวลผลจะถูกยกเลิกก่อนลบ การลบนี้ย้อนกลับไม่ได้")) return;
    el.btnDeleteAllHistory.disabled = true;
    try {
      const res = await fetch("/api/admin/jobs", { method: "DELETE" });
      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || "ลบงานทั้งหมดไม่สำเร็จ");
      }
      const data = await res.json();
      if (data.deleted_jobs.includes(state.uploadedJob?.job_id)) resetFileSelection();
      if (data.deleted_jobs.includes(state.currentJobId)) {
        clearInterval(state.pollTimer);
        state.pollTimer = null;
        state.currentJobId = null;
        state.jobStatus = null;
        state.currentPageData = null;
        state.hasUnsavedChanges = false;
        el.sectionProgress.classList.add("hidden");
        el.sectionWorkspace.classList.add("hidden");
        htmlWorkspace.syncJob();
        refreshExportContext();
      }
      await loadJobHistory();
      el.historyMessage.textContent = `ลบแล้ว ${data.deleted_count} งาน${data.failed_jobs.length ? ` · ลบไม่สำเร็จ ${data.failed_jobs.length} งาน: ${data.failed_jobs.map(job => `${job.job_id}: ${job.detail}`).join("; ")}` : " · ลบงานทั้งหมดแล้ว"}`;
    } catch (err) {
      alert(`ลบงานทั้งหมดไม่สำเร็จ: ${err.message}`);
    } finally {
      el.btnDeleteAllHistory.disabled = false;
    }
  }

  /* ==========================================================================
     Dual-Pane Workspace: Page Viewer & Image Overlays
     ========================================================================== */

  function updatePageSelector(pages) {
    el.pageSelect.innerHTML = "";
    pages.forEach(page => {
      const opt = document.createElement("option");
      opt.value = page.page_id;
      opt.textContent = page.page_num;
      el.pageSelect.appendChild(opt);
    });
    el.pageTotalLabel.textContent = `ทั้งหมด ${pages.length} หน้า`;
  }

  async function switchPage(pageNum) {
    if (!state.jobStatus) return;
    const pageIndex = state.selectedPageIds.indexOf(pageNum);
    if (pageIndex === -1) return;

    // Check unsaved changes before switching
    if (state.hasUnsavedChanges) {
      if (!confirm("คุณมีการแก้ไขที่ยังไม่ได้บันทึก หากเปลี่ยนหน้าข้อความที่แก้ไขจะหายไป ต้องการเปลี่ยนหน้าหรือไม่?")) {
        return;
      }
    }

    state.currentPageNum = pageNum;
    el.pageSelect.value = pageNum;
    el.btnPrevPage.disabled = pageIndex <= 0;
    el.btnNextPage.disabled = pageIndex >= state.selectedPageIds.length - 1;

    await loadPageData(state.currentJobId, pageNum);
  }

  function switchPageByOffset(offset) {
    const currentIndex = state.selectedPageIds.indexOf(state.currentPageNum);
    const nextPage = state.selectedPageIds[currentIndex + offset];
    if (nextPage !== undefined) switchPage(nextPage);
  }

  function updateRangeButton() {
    if (!state.uploadedJob || !el.inputPageStart || !el.inputPageEnd || !el.pageRangeLimit) return;
    const start = Number.parseInt(el.inputPageStart.value, 10);
    const end = Number.parseInt(el.inputPageEnd.value, 10);
    const count = end - start + 1;
    const valid = Number.isInteger(start) && Number.isInteger(end) && start >= 1 && end >= start && end <= state.uploadedJob.total_pages;
    el.btnStartJob.disabled = !valid;
    if (el.btnStartJobHtml) el.btnStartJobHtml.disabled = !valid;
    const canExportImages = valid && state.selectedFile?.name.toLowerCase().endsWith(".pdf");
    el.btnDownloadPageImages.disabled = !canExportImages;
    if (canExportImages) {
      el.btnDownloadPageImages.dataset.downloadUrl = `/api/jobs/${state.uploadedJob.job_id}/download/page-images.zip?page_start=${start}&page_end=${end}`;
    } else {
      delete el.btnDownloadPageImages.dataset.downloadUrl;
    }
    const totalBatches = Math.ceil(count / 200);
    el.pageRangeLimit.textContent = valid
      ? `เลือก ${count} หน้า • ระบบแบ่ง ${totalBatches} batch ละ 200 หน้า`
      : "ช่วงหน้าไม่ถูกต้อง";
    if (valid) {
      el.btnStartJob.innerHTML = `<span>OCR เป็น Text • หน้า ${start}–${end}</span>`;
      if (el.btnStartJobHtml) el.btnStartJobHtml.innerHTML = `<span>OCR เป็น HTML • หน้า ${start}–${end}</span>`;
    }
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

  function refreshExportContext() {
    const hasJob = Boolean(state.currentJobId);
    document.querySelectorAll("[data-export-controls]").forEach(node => { node.disabled = !hasJob; });
    document.querySelectorAll("[data-export-empty]").forEach(node => node.classList.toggle("hidden", hasJob));
    document.querySelectorAll("[data-export-job]").forEach(node => { node.textContent = hasJob ? `${state.jobStatus?.filename || ""} · ${state.currentJobId}` : "ยังไม่ได้เลือกงาน"; });
  }

  function updateDownloadLinks(job) {
    htmlWorkspace.syncJob();
    refreshExportContext();
    const jId = job.job_id;
    el.btnDownloadRaw.href = `/api/jobs/${jId}/download/raw.txt`;
    el.btnDownloadCorrected.href = `/api/jobs/${jId}/download/corrected.txt`;
    el.btnDownloadFinal.href = `/api/jobs/${jId}/download/final.txt`;
    el.btnDownloadBundle.href = `/api/jobs/${jId}/download/bundle.zip`;
    el.btnDownloadCorrected.classList.toggle("hidden", !job.enable_ai);

    // Also refresh HTML export links/badge
    loadHtmlExportStatus();
    loadEpubExportStatus();
    structuredWorkspace.syncJob();

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
