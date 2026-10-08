"use strict";
window.createStructuredWorkspace = ({state}) => {
  const byId = id => document.getElementById(id);
  const ui = {
    button: byId("btn-generate-structured"), status: byId("structured-status-badge"),
    details: byId("structured-details"), page: byId("structured-page-select"),
    resultMode: byId("structured-result-mode"),
    frame: byId("structured-preview-frame"), image: byId("structured-source-image"),
    canvas: byId("structured-source-canvas"), overlay: byId("structured-bbox-overlay"),
    zoomIn: byId("btn-structured-zoom-in"), zoomOut: byId("btn-structured-zoom-out"),
    zoomLabel: byId("structured-zoom-label"),
    sourcePane: byId("structured-source-pane"), resultPane: byId("structured-result-pane"),
    mobileSource: byId("btn-structured-mobile-source"), mobileResult: byId("btn-structured-mobile-result"),
    editHtml: byId("btn-edit-structured-html"),
    links: [byId("btn-dl-structured-text"), byId("btn-dl-structured-html"), byId("btn-dl-structured-layout")],
  };
  let loadedJob = null, documentLayout = null, previewHtml = "";
  let reference = {width: 1, height: 1}, zoom = 1, requestVersion = 0;

  function setStatus(label, kind = "neutral") {
    if (!ui.status) return;
    ui.status.textContent = label;
    ui.status.className = `badge badge-${kind}`;
  }
  function hideDownloads() {
    ui.links.forEach(link => link?.classList.add("hidden"));
    ui.editHtml?.classList.add("hidden");
  }
  function showDownloads(jobId) {
    ["text", "html", "layout"].forEach((variant, index) => {
      const link = ui.links[index];
      if (!link) return;
      link.href = `/api/jobs/${jobId}/export/structured/${variant}`;
      link.classList.remove("hidden");
    });
    ui.editHtml?.classList.remove("hidden");
  }
  function syncJob() {
    if (loadedJob === state.currentJobId) return;
    loadedJob = state.currentJobId;
    documentLayout = null; previewHtml = "";
    if (ui.frame) ui.frame.srcdoc = "";
    if (ui.image) ui.image.removeAttribute("src");
    if (ui.page) ui.page.replaceChildren();
    hideDownloads(); setStatus("ยังไม่ได้สร้าง");
  }
  function applyZoom() {
    if (ui.canvas) ui.canvas.style.width = `${zoom * 100}%`;
    if (ui.zoomLabel) ui.zoomLabel.textContent = `${Math.round(zoom * 100)}%`;
  }
  function showMobilePane(name) {
    ui.sourcePane?.classList.toggle("structured-mobile-hidden", name !== "source");
    ui.resultPane?.classList.toggle("structured-mobile-hidden", name !== "result");
    ui.mobileSource?.setAttribute("aria-pressed", String(name === "source"));
    ui.mobileResult?.setAttribute("aria-pressed", String(name === "result"));
  }
  function drawBbox(bbox, label) {
    if (!ui.overlay || !bbox) return;
    const xs = [bbox.x1, bbox.x2, bbox.x3, bbox.x4].map(Number);
    const ys = [bbox.y1, bbox.y2, bbox.y3, bbox.y4].map(Number);
    const x = Math.min(...xs), y = Math.min(...ys);
    const width = Math.max(...xs) - x, height = Math.max(...ys) - y;
    ui.overlay.setAttribute("viewBox", `0 0 ${reference.width} ${reference.height}`);
    ui.overlay.innerHTML = `<rect x="${x}" y="${y}" width="${width}" height="${height}" rx="2"></rect>`;
    if (ui.details) ui.details.textContent = `${label || "เลือก block"} · bbox ${Math.round(x)}, ${Math.round(y)}, ${Math.round(width)}×${Math.round(height)}`;
  }
  function attachPreviewSelection() {
    let doc;
    try { doc = ui.frame?.contentDocument; } catch (_) { return; }
    if (!doc) return;
    const selectedPage = String(ui.page?.value || "1");
    doc.querySelectorAll("section[data-page]").forEach(section => { section.hidden = section.dataset.page !== selectedPage; });
    doc.querySelectorAll("[data-bbox]").forEach(node => {
      node.tabIndex = 0;
      const select = () => {
        const label = node.dataset.cellId || node.dataset.blockId || "block";
        try {
          const bbox = JSON.parse(node.dataset.bbox);
          if (!bbox) {
            ui.overlay.innerHTML = "";
            ui.details.textContent = `${label} · ไม่มี bbox ที่เชื่อถือได้`;
            return;
          }
          drawBbox(bbox, label);
        } catch (_) { ui.details.textContent = `${label} · อ่าน bbox ไม่สำเร็จ`; }
      };
      node.addEventListener("click", select);
      node.addEventListener("keydown", event => {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); select(); }
      });
    });
  }
  function escaped(value) {
    return String(value || "").replace(/[&<>]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;"})[char]);
  }
  function renderResult() {
    const mode = ui.resultMode?.value || "html";
    if (mode === "html") {
      ui.frame.onload = attachPreviewSelection;
      ui.frame.srcdoc = previewHtml;
      return;
    }
    const pageId = Number(ui.page?.value || 1);
    const page = documentLayout?.pages?.find(item => Number(item.page_id) === pageId);
    const value = page?.text_variants?.[mode];
    const message = value === undefined ? `[ไม่มีผล ${mode} สำหรับหน้านี้]` : value;
    ui.frame.onload = null;
    ui.frame.srcdoc = `<!doctype html><html lang="th"><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"><style>body{font-family:system-ui,sans-serif;margin:1rem}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><pre>${escaped(message)}</pre></html>`;
  }
  async function showPage() {
    if (!state.currentJobId || !documentLayout || !ui.page?.value) return;
    const jobId = state.currentJobId, pageId = Number(ui.page.value);
    ui.overlay.innerHTML = "";
    ui.image.src = `/api/jobs/${jobId}/pages/${pageId}/image`;
    try {
      const response = await fetch(`/api/jobs/${jobId}/pages/${pageId}/data`, {cache: "no-store"});
      if (response.ok) reference = (await response.json()).reference_image || reference;
    } catch (_) { /* the source image can still be shown */ }
    if (previewHtml) renderResult();
  }
  async function loadArtifacts(jobId, version) {
    const [layoutResponse, htmlResponse] = await Promise.all([
      fetch(`/api/jobs/${jobId}/export/structured/layout`, {cache: "no-store"}),
      fetch(`/api/jobs/${jobId}/export/structured/html`, {cache: "no-store"}),
    ]);
    if (!layoutResponse.ok || !htmlResponse.ok) throw new Error("อ่าน structured artifact ไม่สำเร็จ");
    const layout = await layoutResponse.json(), markup = await htmlResponse.text();
    if (version !== requestVersion || jobId !== state.currentJobId) return;
    documentLayout = layout; previewHtml = markup;
    ui.page.replaceChildren(...layout.pages.map(page => {
      const option = document.createElement("option");
      option.value = page.page_id; option.textContent = `หน้า ${page.page_id}`;
      return option;
    }));
    if (layout.pages.length) await showPage();
  }
  async function loadStatus() {
    if (!state.currentJobId) return;
    syncJob();
    const jobId = state.currentJobId, version = ++requestVersion;
    try {
      const response = await fetch(`/api/jobs/${jobId}/export/structured/status`, {cache: "no-store"});
      if (!response.ok) return;
      const status = await response.json();
      if (version !== requestVersion || jobId !== state.currentJobId) return;
      if (status.status === "stale") {
        setStatus("ผลลัพธ์ล้าสมัย — สร้างใหม่", "warning"); hideDownloads();
        ui.details.textContent = "ข้อความ OCR/ข้อความแก้ไขเปลี่ยนหลังสร้าง structured export";
        return;
      }
      if (status.status !== "ready") { setStatus("ยังไม่ได้สร้าง"); hideDownloads(); return; }
      setStatus(`พร้อม ${status.pages || 0} หน้า`, status.unresolved_count ? "warning" : "success");
      ui.details.textContent = `layout ${status.layout_schema_version} · revision ${status.layout_revision} · unresolved ${status.unresolved_count || 0}`;
      showDownloads(jobId);
      await loadArtifacts(jobId, version);
    } catch (error) { console.error("Structured status error:", error); }
  }
  async function generate() {
    if (!state.currentJobId) return;
    const jobId = state.currentJobId, original = ui.button.textContent;
    ui.button.disabled = true; ui.button.textContent = "กำลังสร้าง..."; setStatus("กำลังสร้าง", "warning");
    try {
      const response = await fetch(`/api/jobs/${jobId}/export/structured`, {method: "POST"});
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "สร้าง structured export ไม่สำเร็จ");
      if (jobId === state.currentJobId) await loadStatus();
    } catch (error) { setStatus("สร้างไม่สำเร็จ", "warning"); alert(error.message); }
    finally { ui.button.disabled = !state.currentJobId; ui.button.textContent = original; }
  }
  function init() {
    ui.button?.addEventListener("click", generate);
    ui.page?.addEventListener("change", showPage);
    ui.resultMode?.addEventListener("change", renderResult);
    ui.zoomIn?.addEventListener("click", () => { zoom = Math.min(2.5, zoom + .25); applyZoom(); });
    ui.zoomOut?.addEventListener("click", () => { zoom = Math.max(.5, zoom - .25); applyZoom(); });
    ui.mobileSource?.addEventListener("click", () => showMobilePane("source"));
    ui.mobileResult?.addEventListener("click", () => showMobilePane("result"));
    showMobilePane("source");
    applyZoom();
  }
  return {init, loadStatus, syncJob, generate};
};
