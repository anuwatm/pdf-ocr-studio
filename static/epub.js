"use strict";
window.createEpubWorkspace = ({state, el}) => {
  let loadedJob = null;
  let requestVersion = 0;
  let building = false;
  let persistedCover = null;
  let tocState = null;
  let tocDirty = false;
  const tocDrafts = new Map();
  const field = id => document.getElementById(id);
  const extraFields = ['epub-identifier', 'epub-date', 'epub-description', 'epub-cover', 'epub-cover-alt', 'epub-remove-cover'];
  extraFields.forEach(id => field(id)?.addEventListener('input', () => {
    state.epubConfigDirty = true;
    state.epubPreviewRevision = null;
    el.btnBuildEpub.disabled = true;
    el.epubExportStatusBadge.textContent = 'ตั้งค่าเปลี่ยน — สร้าง Preview ใหม่';
    el.epubExportStatusBadge.className = 'badge badge-warning';
    [el.btnDlEpub, el.btnDownloadEpub].forEach(link => link?.classList.add('hidden'));
  }));
  function syncJob() {
    if (loadedJob === state.currentJobId) return;
    if (loadedJob && tocState) tocDrafts.set(loadedJob, {tocState: structuredClone(tocState), tocDirty});
    loadedJob = state.currentJobId;
    persistedCover = null;
    state.epubConfigDirty = false;
    state.epubPreviewRevision = null;
    for (const input of [el.epubTitle, el.epubCreator, el.epubPublisher]) input.value = "";
    el.epubLanguage.value = "th";
    el.epubSourceVariant.value = "auto";
    el.epubChapterSplit.value = "heading";
    el.epubPreviewFrame.srcdoc = "";
    el.epubSourceEditor.value = "";
    el.btnBuildEpub.disabled = true;
    extraFields.forEach(id => { if (field(id)) { field(id).value = ''; if (field(id).type === 'checkbox') field(id).checked = false; } });
    for (const link of [el.btnDlEpub, el.btnDownloadEpub]) link.classList.add("hidden");
    const draft = loadedJob ? tocDrafts.get(loadedJob) : null;
    tocState = draft?.tocState || null;
    tocDirty = Boolean(draft?.tocDirty);
    renderToc();
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
    const config = {
      source_variant: el.epubSourceVariant?.value || "auto",
      chapter_split: el.epubChapterSplit?.value || "heading",
      metadata: {
        title: el.epubTitle?.value.trim() || "",
        creator: el.epubCreator?.value.trim() || "",
        publisher: el.epubPublisher?.value.trim() || "",
        language: el.epubLanguage?.value.trim() || "th",
        identifier: field('epub-identifier')?.value.trim() || '',
        description: field('epub-description')?.value.trim() || '',
        date: field('epub-date')?.value || '',
      },
    };
    if (tocState?.toc_revision && !tocDirty) config.toc_revision = tocState.toc_revision;
    return config;
  }

  function markTocDirty() {
    tocDirty = true;
    state.epubConfigDirty = true;
    state.epubPreviewRevision = null;
    el.btnBuildEpub.disabled = true;
    field('btn-save-epub-toc').disabled = false;
    field('epub-toc-status').textContent = 'มีฉบับร่างที่ยังไม่บันทึก · Package ถูกบล็อก';
    el.epubExportStatusBadge.textContent = 'สารบัญเปลี่ยน — บันทึกและสร้าง Preview ใหม่';
    el.epubExportStatusBadge.className = 'badge badge-warning';
  }

  function normalizeTocHierarchy() {
    if (!tocState) return;
    const stack = [];
    tocState.entries.forEach((entry, index) => {
      entry.order = index;
      entry.level = Math.max(1, Math.min(3, Number(entry.level) || 1));
      while (stack.length >= entry.level) stack.pop();
      if (entry.level > 1 && !stack[entry.level - 2]) entry.level = 1;
      entry.parent_id = entry.level > 1 ? stack[entry.level - 2]?.entry_id || null : null;
      stack[entry.level - 1] = entry;
      stack.length = entry.level;
    });
  }

  function renderToc() {
    const list = field('epub-toc-list');
    if (!list) return;
    list.replaceChildren();
    if (!tocState) {
      field('btn-save-epub-toc').disabled = true;
      return;
    }
    const targets = tocState.targets || [];
    tocState.entries.forEach((entry, index) => {
      const row = document.createElement('div');
      row.className = 'toc-row' + (entry.status === 'unresolved' ? ' toc-row-unresolved' : '');
      row.dataset.level = entry.level;
      row.dataset.entryId = entry.entry_id;
      const label = document.createElement('input');
      label.value = entry.label || '';
      label.maxLength = 300;
      label.setAttribute('aria-label', `ชื่อสารบัญรายการ ${index + 1}`);
      label.addEventListener('input', () => { entry.label = label.value; entry.status = 'user-edited'; markTocDirty(); });
      const level = document.createElement('select');
      level.setAttribute('aria-label', `ระดับรายการ ${index + 1}`);
      [1,2,3].forEach(value => level.add(new Option(`ระดับ ${value}`, String(value))));
      level.value = String(entry.level || 1);
      level.addEventListener('change', () => { entry.level = Number(level.value); normalizeTocHierarchy(); markTocDirty(); renderToc(); });
      const target = document.createElement('select');
      target.setAttribute('aria-label', `ปลายทางรายการ ${index + 1}`);
      target.add(new Option('— เลือกปลายทาง —', ''));
      targets.forEach(item => target.add(new Option(item.context, item.target_id)));
      target.value = entry.target_id || '';
      target.addEventListener('change', () => {
        entry.target_id = target.value;
        entry.target_match_key = targets.find(item => item.target_id === target.value)?.match_key || '';
        entry.status = target.value ? 'user-edited' : 'unresolved';
        markTocDirty(); renderToc();
      });
      const actions = document.createElement('div');
      actions.className = 'toc-row-actions';
      const action = (text, title, handler) => {
        const button = document.createElement('button'); button.type = 'button'; button.className = 'btn btn-outline btn-xs';
        button.textContent = text; button.title = title; button.setAttribute('aria-label', title);
        button.addEventListener('click', handler); actions.appendChild(button);
      };
      action('↑', 'เลื่อนขึ้น', () => { if (index) [tocState.entries[index-1], tocState.entries[index]] = [entry, tocState.entries[index-1]]; normalizeTocHierarchy(); markTocDirty(); renderToc(); });
      action('↓', 'เลื่อนลง', () => { if (index < tocState.entries.length-1) [tocState.entries[index+1], tocState.entries[index]] = [entry, tocState.entries[index+1]]; normalizeTocHierarchy(); markTocDirty(); renderToc(); });
      action('−', 'ลดระดับ', () => { entry.level = Math.max(1, entry.level-1); normalizeTocHierarchy(); markTocDirty(); renderToc(); });
      action('+', 'เพิ่มระดับ', () => { entry.level = Math.min(3, entry.level+1); normalizeTocHierarchy(); markTocDirty(); renderToc(); });
      action('ดู', 'ไปดูตำแหน่ง', () => { const item = targets.find(item => item.target_id === entry.target_id); if (item && el.epubPreviewFrame?.contentWindow) { switchEpubSubtab('preview'); el.epubPreviewFrame.contentWindow.location.hash = item.preview_fragment; } });
      action('×', 'เอารายการออก', () => { tocState.entries.splice(index, 1); normalizeTocHierarchy(); markTocDirty(); renderToc(); });
      row.append(label, level, target, actions); list.appendChild(row);
    });
    const unresolved = tocState.entries.filter(entry => !targets.some(target => target.target_id === entry.target_id)).length;
    field('epub-toc-status').textContent = `${tocState.entries.length} รายการ · matched ${tocState.matched_count ?? tocState.entries.length} · unresolved ${unresolved}${tocDirty ? ' · ยังไม่บันทึก' : ''}`;
    field('btn-save-epub-toc').disabled = !tocDirty;
    const conflict = field('epub-toc-conflict');
    conflict?.classList.toggle('hidden', !tocState.source_changed && !unresolved);
    if (conflict && (tocState.source_changed || unresolved)) conflict.textContent = `HTML เปลี่ยน: จับคู่ได้ ${tocState.matched_count || 0}, unresolved ${unresolved} กรุณาเลือก target ที่หายก่อนบันทึก`;
  }

  async function loadTocEditor(force=false) {
    if (!state.currentJobId) return;
    if (tocDirty && !force && !confirm('มีฉบับร่างสารบัญค้างอยู่ ต้องการ re-match กับ HTML ปัจจุบันหรือไม่?')) return;
    const jobId = state.currentJobId, version = ++requestVersion;
    const params = new URLSearchParams({source_variant: el.epubSourceVariant.value || 'auto', chapter_split: el.epubChapterSplit.value || 'heading'});
    const response = await fetch(`/api/jobs/${jobId}/export/epub/toc?${params}`, {cache:'no-store'});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'โหลดสารบัญไม่สำเร็จ');
    if (jobId !== state.currentJobId || version !== requestVersion) return;
    tocState = data; tocDirty = Boolean(data.source_changed || data.unresolved?.length);
    renderToc();
  }

  async function saveTocEditor() {
    if (!tocState || !state.currentJobId) return;
    normalizeTocHierarchy();
    const response = await fetch(`/api/jobs/${state.currentJobId}/export/epub/toc`, {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({
      entries: tocState.entries, base_source_revision: tocState.source_revision,
      base_toc_revision: tocState.toc_revision, base_preview_revision: tocState.base_preview_revision,
      source_variant: el.epubSourceVariant.value || 'auto', chapter_split: el.epubChapterSplit.value || 'heading'
    })});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'บันทึกสารบัญไม่สำเร็จ');
    tocState.toc_revision = data.toc.toc_revision; tocState.source_changed = false;
    tocState.unresolved = []; tocState.matched_count = tocState.entries.length; tocDirty = false;
    state.epubConfigDirty = false; renderToc(); await generateEpubPreview();
  }

  async function regenerateTocEditor() {
    if (!tocState) await loadTocEditor();
    if (!tocState || !confirm('สร้างสารบัญอัตโนมัติใหม่และทับรายการที่แก้ไว้หรือไม่?')) return;
    const response = await fetch(`/api/jobs/${state.currentJobId}/export/epub/toc/regenerate`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({
      confirm:true, base_source_revision:tocState.source_revision, base_toc_revision:tocState.toc_revision,
      base_preview_revision:tocState.base_preview_revision, source_variant:el.epubSourceVariant.value || 'auto',
      chapter_split:el.epubChapterSplit.value || 'heading'
    })});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'สร้างสารบัญอัตโนมัติไม่สำเร็จ');
    tocDirty = false; await loadTocEditor(true); state.epubConfigDirty = false; await generateEpubPreview();
  }

  function addTocEntry() {
    if (!tocState) return;
    const used = new Set(tocState.entries.map(entry => entry.target_id));
    const target = tocState.targets.find(item => !used.has(item.target_id));
    if (!target) { alert('ไม่มี target ที่ยังไม่ได้ใช้'); return; }
    tocState.entries.push({entry_id:`toc-user-${crypto.randomUUID().replaceAll('-','').slice(0,12)}`, label:target.label,
      parent_id:null, level:1, order:tocState.entries.length, target_id:target.target_id,
      target_match_key:target.match_key, status:'user-edited'});
    markTocDirty(); renderToc();
  }

  function showCoverFile(file) {
    if (!file) return;
    const image = field('epub-cover-thumbnail');
    const url = URL.createObjectURL(file); image.src = url; image.classList.remove('hidden');
    const probe = new Image(); probe.onload = () => { field('epub-cover-details').textContent = `${file.type} · ${probe.width}×${probe.height} · ${(file.size/1024).toFixed(1)} KB · ยังไม่บันทึก`; URL.revokeObjectURL(url); }; probe.src = url;
  }

  async function loadEpubPreviewContent(jobId, version) {
    if (!jobId) return;
    const res = await fetch(`/api/jobs/${jobId}/export/epub/preview`, { cache: "no-store" });
    if (!res.ok) return;
    const xhtml = await res.text();
    if (jobId !== state.currentJobId || version !== requestVersion) return;
    // srcdoc inherits the parent base URL; plain #fragment would reload the app.
    if (el.epubPreviewFrame) el.epubPreviewFrame.srcdoc = xhtml.replace(/href="#/g, 'href="about:srcdoc#');
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
      if (field('epub-preview-details')) {
        field('epub-preview-details').textContent = status.preview_revision
          ? `ต้นทาง ${status.source_variant}.html · revision ${status.preview_revision} · ${status.chapters_count || 0} บท${status.cover ? ' · มีปก' : ''}` : '';
      }
      const previewUsable = Boolean(status.preview_ready && status.status !== 'generating' && !status.is_stale && status.preview_revision && !state.epubConfigDirty);
      state.epubPreviewRevision = previewUsable ? status.preview_revision : null;

      if (el.btnBuildEpub) el.btnBuildEpub.disabled = building || !previewUsable;
      if (el.epubExportStatusBadge) {
        if (status.status === 'generating') {
          el.epubExportStatusBadge.textContent = 'กำลังสร้าง EPUB/Preview...';
          el.epubExportStatusBadge.className = 'badge badge-warning';
        } else if (state.epubConfigDirty) {
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
        } else if (['failed', 'invalid'].includes(status.status)) {
          el.epubExportStatusBadge.textContent = `สร้างไม่สำเร็จ: ${status.last_error || status.status}`;
          el.epubExportStatusBadge.className = 'badge badge-warning';
        } else {
          el.epubExportStatusBadge.textContent = "ยังไม่ได้ Preview";
          el.epubExportStatusBadge.className = "badge badge-neutral";
        }
      }

      if (status.metadata && !state.epubConfigDirty) {
        persistedCover = status.cover || null;
        for (const name of ['identifier', 'date', 'description']) {
          if (field(`epub-${name}`)) field(`epub-${name}`).value = status.metadata[name] || '';
        }
        if (field('epub-cover-alt') && persistedCover) field('epub-cover-alt').value = persistedCover.alt || '';
        if (persistedCover && !field('epub-cover')?.files?.length) {
          const thumb = field('epub-cover-thumbnail');
          thumb.src = `/api/jobs/${jobId}/export/epub/cover?revision=${encodeURIComponent(status.preview_revision || '')}`;
          thumb.classList.remove('hidden');
          field('epub-cover-details').textContent = `image/png · ${persistedCover.width}×${persistedCover.height} · Preview ที่บันทึกแล้ว`;
        }
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
        link.classList.toggle("hidden", !status.epub_ready || status.is_stale || status.package_is_stale || state.epubConfigDirty);
      });
      if (status.preview_ready) await loadEpubPreviewContent(jobId, version);
    } catch (err) {
      console.error("Load EPUB status error:", err);
    }
  }

  async function generateEpubPreview() {
    if (!state.currentJobId) return;
    if (tocDirty) { alert("กรุณาบันทึกหรือยกเลิกฉบับร่างสารบัญก่อนสร้าง Preview"); return; }
    if (state.htmlDirty) { alert("กรุณาบันทึก Final HTML ก่อนสร้าง EPUB Preview"); return; }
    const button = el.btnGenerateEpubPreview;
    const jobId = state.currentJobId;
    const fingerprint = () => JSON.stringify([collectEpubConfig(), field('epub-cover-alt')?.value, field('epub-remove-cover')?.checked]);
    const configFingerprint = fingerprint();
    const originalCover = field('epub-cover')?.files?.[0];
    const originalText = button?.textContent || "";
    if (button) {
      button.disabled = true;
      button.textContent = "กำลังสร้าง Preview...";
    }
    if (el.btnBuildEpub) el.btnBuildEpub.disabled = true;
    try {
      const config = collectEpubConfig();
      const coverFile = field('epub-cover')?.files?.[0];
      const removeCover = Boolean(field('epub-remove-cover')?.checked);
      if (!removeCover && coverFile) {
        if (!['image/png', 'image/jpeg'].includes(coverFile.type) || coverFile.size > 2 * 1024 * 1024) {
          throw new Error('รูปปกต้องเป็น PNG/JPEG ไม่เกิน 2 MB');
        }
        const bytes = new Uint8Array(await coverFile.arrayBuffer());
        let binary = '';
        for (let offset = 0; offset < bytes.length; offset += 8192) binary += String.fromCharCode(...bytes.subarray(offset, offset + 8192));
        config.cover = {data_base64: btoa(binary), alt: field('epub-cover-alt')?.value.trim() || 'ปกหนังสือ'};
      } else if (!removeCover && persistedCover) {
        config.cover = {reuse: true, alt: field('epub-cover-alt')?.value.trim() || persistedCover.alt};
      }
      if (jobId !== state.currentJobId) return;
      const res = await fetch(`/api/jobs/${jobId}/export/epub/preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      });
      const data = await res.json();
      if (jobId !== state.currentJobId) return;
      if (!res.ok) throw new Error(data.detail || "สร้าง XHTML Quick Preview ไม่สำเร็จ");
      state.epubConfigDirty = configFingerprint !== fingerprint() || originalCover !== field('epub-cover')?.files?.[0];
      state.epubPreviewRevision = state.epubConfigDirty ? null : data.meta?.preview_revision || null;
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
    if (building) return;
    if (state.htmlDirty) { alert("กรุณาบันทึก Final HTML แล้วสร้าง Preview ใหม่ก่อนสร้าง EPUB"); return; }
    if (!state.currentJobId || !state.epubPreviewRevision) {
      alert("กรุณาสร้าง XHTML Quick Preview ก่อน");
      return;
    }
    const button = el.btnBuildEpub;
    const jobId = state.currentJobId;
    const previewRevision = state.epubPreviewRevision;
    building = true;
    const originalText = button?.textContent || "";
    if (button) {
      button.disabled = true;
      button.textContent = "กำลังสร้าง EPUB...";
    }
    try {
      const res = await fetch(`/api/jobs/${jobId}/export/epub`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ base_preview_revision: previewRevision }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "สร้าง EPUB ไม่สำเร็จ");
      if (!data.meta?.epub_ready) throw new Error("เซิร์ฟเวอร์ยังไม่ได้ยืนยันว่าไฟล์ EPUB พร้อมดาวน์โหลด");
      if (jobId !== state.currentJobId) return;
      await loadEpubExportStatus();
      if (jobId !== state.currentJobId) return;
      // The package response confirms the file exists. Do not require a
      // second manual click or let a failed status refresh hide the download.
      const downloadUrl = `/api/jobs/${jobId}/export/epub/download`;
      for (const link of [el.btnDlEpub, el.btnDownloadEpub]) {
        link.href = downloadUrl;
        link.classList.remove("hidden");
      }
      el.epubExportStatusBadge.textContent = "สร้าง EPUB แล้ว · เริ่มดาวน์โหลด";
      el.epubExportStatusBadge.className = "badge badge-success";
      const fileRes = await fetch(downloadUrl, {cache: "no-store"});
      if (!fileRes.ok) throw new Error(`ดาวน์โหลด EPUB ไม่สำเร็จ (HTTP ${fileRes.status})`);
      if (!fileRes.headers.get("Content-Type")?.includes("application/epub+zip")) {
        throw new Error("เซิร์ฟเวอร์ไม่ได้ส่งไฟล์ EPUB กลับมา");
      }
      const blob = await fileRes.blob();
      if (!blob.size) throw new Error("ไฟล์ EPUB ที่ได้รับว่างเปล่า");
      const disposition = fileRes.headers.get("Content-Disposition") || "";
      const encodedName = disposition.match(/filename\*=UTF-8''([^;]+)/i);
      const quotedName = disposition.match(/filename="([^"]+)"/i);
      let filename = `${(state.jobStatus?.filename || "document").replace(/\.[^.]+$/, "")}.epub`;
      if (encodedName) {
        try { filename = decodeURIComponent(encodedName[1]); } catch (_) { /* Use fallback name. */ }
      } else if (quotedName) filename = quotedName[1];
      const objectUrl = URL.createObjectURL(blob);
      const download = document.createElement("a");
      download.href = objectUrl;
      download.download = filename;
      document.body.appendChild(download);
      download.click();
      download.remove();
      setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
    } catch (err) {
      alert(`สร้างหรือดาวน์โหลด EPUB ไม่สำเร็จ: ${err.message}`);
      await loadEpubExportStatus();
    } finally {
      building = false;
      if (button) {
        button.disabled = !state.epubPreviewRevision;
        button.textContent = originalText;
      }
    }
  }

  field('btn-load-epub-toc')?.addEventListener('click', () => loadTocEditor().catch(error => alert(error.message)));
  field('btn-add-epub-toc')?.addEventListener('click', addTocEntry);
  field('btn-save-epub-toc')?.addEventListener('click', () => saveTocEditor().catch(error => alert(error.message)));
  field('btn-regenerate-epub-toc')?.addEventListener('click', () => regenerateTocEditor().catch(error => alert(error.message)));
  [el.epubSourceVariant, el.epubChapterSplit].filter(Boolean).forEach(input => input.addEventListener('change', () => {
    if (tocState) { tocDirty = true; field('epub-toc-status').textContent = 'ต้นทางหรือการแบ่งบทเปลี่ยน · โหลดเพื่อ re-match โดยฉบับร่างเดิมยังคงอยู่'; renderToc(); }
  }));
  const coverInput = field('epub-cover'), coverDrop = field('epub-cover-drop');
  coverInput?.addEventListener('change', () => showCoverFile(coverInput.files?.[0]));
  coverDrop?.addEventListener('click', event => { if (event.target !== coverInput) coverInput?.click(); });
  coverDrop?.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); coverInput?.click(); } });
  coverDrop?.addEventListener('dragover', event => { event.preventDefault(); coverDrop.classList.add('dragover'); });
  coverDrop?.addEventListener('dragleave', () => coverDrop.classList.remove('dragover'));
  coverDrop?.addEventListener('drop', event => {
    event.preventDefault(); coverDrop.classList.remove('dragover');
    const file = event.dataTransfer?.files?.[0];
    if (!file || !coverInput) return;
    const transfer = new DataTransfer(); transfer.items.add(file); coverInput.files = transfer.files;
    coverInput.dispatchEvent(new Event('input', {bubbles:true})); showCoverFile(file);
  });
  window.addEventListener('beforeunload', event => { if (tocDirty || state.epubConfigDirty) { event.preventDefault(); event.returnValue = ''; } });

return {switchEpubSubtab, loadEpubExportStatus, generateEpubPreview, buildEpubPackage};
};
