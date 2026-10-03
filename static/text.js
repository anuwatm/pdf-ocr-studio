"use strict";
window.createTextWorkspace = ({state, el, loadPageData}) => {
  function activateTab(tabName) {
    [el.tabFinal, el.tabDiff, el.tabRaw].forEach(t => t?.classList.remove("active"));
    [el.panelFinal, el.panelDiff, el.panelRaw].forEach(p => p?.classList.add("hidden"));

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

return {activateTab, renderProposalsAndDiff, escapeHtml, acceptAllCorrections, revertAllCorrections, saveManualEdit, updateSaveIndicator, updateReviewStatusBadge, markAsReviewed};
};
