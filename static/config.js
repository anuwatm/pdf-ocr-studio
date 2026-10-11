(() => {
  "use strict";

  const el = {
    form: document.getElementById("llm-config-form"),
    transport: document.getElementById("llm-transport"),
    cliProvider: document.getElementById("llm-cli-provider"),
    cliProviderField: document.getElementById("llm-cli-provider-field"),
    baseUrl: document.getElementById("llm-base-url"),
    baseUrlField: document.getElementById("llm-base-url-field"),
    model: document.getElementById("llm-model"),
    apiKey: document.getElementById("llm-api-key"),
    apiKeyField: document.getElementById("llm-api-key-field"),
    apiKeyHint: document.getElementById("api-key-hint"),
    timeout: document.getElementById("llm-timeout"),
    test: document.getElementById("btn-test-connection"),
    save: document.getElementById("btn-save-config"),
    result: document.getElementById("config-result"),
    status: document.getElementById("config-status"),
    themeToggle: document.getElementById("btn-theme-toggle"),
    cliNotice: document.getElementById("llm-cli-notice"),
    cliStatusList: document.getElementById("cli-status-list"),
    cliStatusSummary: document.getElementById("cli-status-summary"),
    cliStatusCheckedAt: document.getElementById("cli-status-checked-at"),
    refreshCliStatus: document.getElementById("btn-refresh-cli-status"),
  };

  const googleEl = {
    form: document.getElementById("google-config-form"),
    project: document.getElementById("google-project"),
    location: document.getElementById("google-location"),
    credentialsPath: document.getElementById("google-credentials-path"),
    credentialsHint: document.getElementById("google-credentials-hint"),
    apiKey: document.getElementById("google-api-key"),
    apiKeyHint: document.getElementById("google-api-key-hint"),
    test: document.getElementById("btn-test-google"),
    save: document.getElementById("btn-save-google"),
    result: document.getElementById("google-config-result"),
    status: document.getElementById("google-config-status"),
  };

  function setTheme() {
    const theme = localStorage.getItem("theme") || "theme-light";
    document.body.className = theme;
    el.themeToggle.addEventListener("click", () => {
      const next = document.body.classList.contains("theme-dark") ? "theme-light" : "theme-dark";
      document.body.className = next;
      localStorage.setItem("theme", next);
    });
  }

  function setResult(message, type) {
    el.result.textContent = message;
    el.result.className = `config-result ${type}`;
  }

  function payload() {
    const key = el.apiKey.value.trim();
    return {
      transport: el.transport.value,
      cli_provider: el.cliProvider.value,
      base_url: el.baseUrl.value.trim(),
      model: el.model.value.trim(),
      timeout: Number(el.timeout.value),
      api_key: key || null,
    };
  }

  function transportChanged() {
    const cli = el.transport.value === "cli";
    el.baseUrl.required = !cli;
    el.baseUrlField.classList.toggle("hidden", cli);
    el.apiKeyField.classList.toggle("hidden", cli);
    el.cliProviderField.classList.toggle("hidden", !cli);
    el.cliNotice.classList.toggle("hidden", !cli);
  }

  function setBusy(busy) {
    el.test.disabled = busy;
    el.save.disabled = busy;
  }

  async function readError(res) {
    const data = await res.json().catch(() => ({}));
    return data.detail || data.error || "ไม่สามารถดำเนินการได้";
  }

  async function loadConfig() {
    try {
      const res = await fetch("/api/ai/config");
      if (!res.ok) throw new Error(await readError(res));
      const config = await res.json();
      el.transport.value = config.transport || "api";
      el.cliProvider.value = config.cli_provider || "codex";
      el.baseUrl.value = config.base_url;
      el.model.value = config.model;
      el.timeout.value = config.timeout;
      transportChanged();
      el.apiKeyHint.textContent = config.api_key_configured
        ? "มี API key ตั้งค่าอยู่แล้ว — เว้นว่างเพื่อเก็บค่าเดิม"
        : "ยังไม่มี API key — เว้นว่างได้สำหรับ Local LLM ส่วนใหญ่";
      el.status.className = "status-badge status-online";
      el.status.textContent = "พร้อมตั้งค่า";
    } catch (error) {
      el.status.className = "status-badge status-offline";
      el.status.textContent = "โหลดค่าไม่สำเร็จ";
      setResult(error.message, "error");
    }
  }

  const stateLabel = {
    ready: "พร้อมใช้งาน",
    needs_auth: "ต้องเข้าสู่ระบบ",
    not_installed: "ไม่พบโปรแกรม",
    not_checked: "ยังไม่ตรวจ",
    error: "ตรวจสอบไม่สำเร็จ",
  };

  const authLabel = {
    ready: "พร้อม",
    required: "ต้องเข้าสู่ระบบ",
    check_on_use: "ตรวจเมื่อใช้งาน",
    not_required: "ไม่ต้องใช้",
    not_checked: "ยังไม่ตรวจ",
  };

  const runtimeLabel = {
    ready: "พร้อม",
    supported: "รองรับ",
    not_ready: "ยังไม่พร้อม",
    not_supported: "ไม่รองรับ Local",
    not_checked: "ยังไม่ตรวจ",
  };

  function statusTone(status) {
    if (status === "ready") return "ready";
    if (status === "needs_auth" || status === "not_checked") return "warning";
    return "error";
  }

  function addDetail(list, label, value) {
    const term = document.createElement("dt");
    const detail = document.createElement("dd");
    term.textContent = label;
    detail.textContent = value || "—";
    list.append(term, detail);
  }

  function renderCliStatus(data) {
    el.cliStatusList.replaceChildren();
    const adapters = Array.isArray(data.adapters) ? data.adapters : [];
    adapters.forEach((adapter) => {
      const card = document.createElement("article");
      card.className = "cli-status-card";
      card.dataset.adapter = adapter.id;

      const head = document.createElement("div");
      head.className = "cli-status-card-head";
      const titleWrap = document.createElement("div");
      const title = document.createElement("h3");
      title.textContent = adapter.label;
      titleWrap.append(title);
      if (adapter.primary) {
        const primary = document.createElement("span");
        primary.className = "cli-status-primary";
        primary.textContent = "ADAPTER หลัก";
        titleWrap.append(primary);
      }
      const badge = document.createElement("span");
      badge.className = `cli-status-state ${statusTone(adapter.status)}`;
      badge.textContent = stateLabel[adapter.status] || adapter.status;
      head.append(titleWrap, badge);

      const details = document.createElement("dl");
      details.className = "cli-status-details";
      addDetail(details, "Command", adapter.command);
      addDetail(details, "Version", adapter.version);
      addDetail(details, "Authentication", authLabel[adapter.authentication] || adapter.authentication);
      addDetail(details, "Local runtime", runtimeLabel[adapter.local_runtime] || adapter.local_runtime);

      card.append(head, details);
      if (adapter.detail || adapter.local_detail) {
        const message = document.createElement("p");
        message.className = "cli-status-message";
        message.textContent = [adapter.detail, adapter.local_detail].filter(Boolean).join("\n");
        card.append(message);
      }
      el.cliStatusList.append(card);
    });
    const ready = adapters.filter((item) => item.status === "ready").length;
    el.cliStatusSummary.textContent = data.checked_at
      ? `ตรวจพบ ${adapters.filter((item) => item.installed).length}/${adapters.length} รายการ · พร้อมใช้งาน ${ready} รายการ`
      : "ยังไม่มีผลตรวจ กด “ตรวจสอบสถานะ” เพื่อเริ่มตรวจ";
    el.cliStatusSummary.className = "config-result info";
    el.cliStatusList.setAttribute("aria-busy", "false");
    el.cliStatusCheckedAt.textContent = data.checked_at
      ? `ตรวจล่าสุด ${new Date(data.checked_at).toLocaleString("th-TH")}` : "";
  }

  async function loadCliStatus(runCheck = false) {
    el.refreshCliStatus.disabled = true;
    el.cliStatusList.setAttribute("aria-busy", "true");
    el.cliStatusSummary.textContent = runCheck ? "กำลังตรวจสอบ Codex, Gemini, AGY, Claude และ LM Studio CLI..." : "กำลังโหลดผลตรวจล่าสุด...";
    el.cliStatusSummary.className = "config-result info";
    try {
      const res = await fetch(runCheck ? "/api/ai/cli/status/check" : "/api/ai/cli/status", { method: runCheck ? "POST" : "GET", cache: "no-store" });
      if (!res.ok) throw new Error(await readError(res));
      renderCliStatus(await res.json());
    } catch (error) {
      el.cliStatusSummary.textContent = error.message;
      el.cliStatusSummary.className = "config-result error";
      el.cliStatusList.setAttribute("aria-busy", "false");
    } finally {
      el.refreshCliStatus.disabled = false;
    }
  }

  async function testConnection() {
    if (!el.form.reportValidity()) return;
    setBusy(true);
    setResult(el.transport.value === "cli" ? `กำลังตรวจ ${el.cliProvider.options[el.cliProvider.selectedIndex].text}...` : "กำลังทดสอบการเชื่อมต่อ Local LLM...", "info");
    try {
      const res = await fetch("/api/ai/config/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload()),
      });
      if (!res.ok) throw new Error(await readError(res));
      const data = await res.json();
      if (data.status === "connected") {
        const channel = data.cli_provider ? `${data.cli_provider.toUpperCase()} CLI` : el.transport.value.toUpperCase();
        setResult(`เชื่อมต่อสำเร็จ (${channel}): ${data.configured_model}`, "success");
      } else {
        setResult(data.error || "พบเซิร์ฟเวอร์ แต่ไม่พบโมเดลที่ระบุ", "error");
      }
    } catch (error) {
      setResult(error.message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function saveConfig(event) {
    event.preventDefault();
    if (!el.form.reportValidity()) return;
    setBusy(true);
    setResult("กำลังบันทึกการตั้งค่า...", "info");
    try {
      const res = await fetch("/api/ai/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload()),
      });
      if (!res.ok) throw new Error(await readError(res));
      const data = await res.json();
      el.apiKey.value = "";
      el.apiKeyHint.textContent = data.api_key_configured
        ? "มี API key ตั้งค่าอยู่แล้ว — เว้นว่างเพื่อเก็บค่าเดิม"
        : "ยังไม่มี API key — เว้นว่างได้สำหรับ Local LLM ส่วนใหญ่";
      setResult("บันทึกแล้ว การแปลงงานใหม่จะใช้ค่านี้ทันที", "success");
    } catch (error) {
      setResult(error.message, "error");
    } finally {
      setBusy(false);
    }
  }

  // ---------------------------------------------------------------------------
  // Google Cloud Translation Config
  // ---------------------------------------------------------------------------

  function setGoogleResult(message, type) {
    if (!googleEl.result) return;
    googleEl.result.textContent = message;
    googleEl.result.className = `config-result ${type}`;
  }

  function setGoogleBusy(busy) {
    if (googleEl.test) googleEl.test.disabled = busy;
    if (googleEl.save) googleEl.save.disabled = busy;
  }

  function googlePayload() {
    return {
      project: googleEl.project.value.trim() || null,
      location: googleEl.location.value.trim() || "global",
      credentials_path: googleEl.credentialsPath.value.trim() || null,
      api_key: googleEl.apiKey.value.trim() || null,
    };
  }

  async function loadGoogleConfig() {
    if (!googleEl.form) return;
    try {
      const res = await fetch("/api/translation/google/config");
      if (!res.ok) throw new Error(await readError(res));
      const config = await res.json();
      googleEl.project.value = config.project || "";
      googleEl.location.value = config.location || "global";
      googleEl.credentialsPath.value = config.credentials_path || "";

      if (config.credentials_configured) {
        googleEl.credentialsHint.textContent = "✓ ตรวจพบไฟล์ Service Account JSON บนเครื่องแล้ว";
        googleEl.credentialsHint.style.color = "var(--color-success, #16a34a)";
      } else if (config.credentials_path) {
        googleEl.credentialsHint.textContent = "⚠ ไม่พบไฟล์ตามพาธที่ระบุ";
        googleEl.credentialsHint.style.color = "var(--color-warning, #d97706)";
      } else {
        googleEl.credentialsHint.textContent = "พาธไฟล์ JSON ของ Google Cloud Service Account บนเครื่อง";
        googleEl.credentialsHint.style.color = "";
      }

      if (config.api_key_configured) {
        googleEl.apiKeyHint.textContent = "มี API Key ตั้งค่าอยู่แล้ว — เว้นว่างเพื่อเก็บค่าเดิม";
      } else {
        googleEl.apiKeyHint.textContent = "ยังไม่มี API Key — เว้นว่างได้หากใช้ Service Account";
      }

      if (config.credentials_configured || config.api_key_configured) {
        googleEl.status.className = "status-badge status-online";
        googleEl.status.textContent = config.credentials_configured ? "พร้อมใช้งาน (v3)" : "พร้อมใช้งาน (v2)";
      } else {
        googleEl.status.className = "status-badge status-checking";
        googleEl.status.textContent = "ยังไม่ได้ตั้งค่า";
      }
    } catch (error) {
      if (googleEl.status) {
        googleEl.status.className = "status-badge status-offline";
        googleEl.status.textContent = "โหลดค่าไม่สำเร็จ";
      }
      setGoogleResult(error.message, "error");
    }
  }

  async function testGoogleConnection() {
    if (!googleEl.form.reportValidity()) return;
    setGoogleBusy(true);
    setGoogleResult("กำลังทดสอบการแปล Google Cloud Translation...", "info");
    try {
      const res = await fetch("/api/translation/google/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(googlePayload()),
      });
      if (!res.ok) throw new Error(await readError(res));
      const data = await res.json();
      if (data.status === "connected") {
        setGoogleResult(data.message || `เชื่อมต่อสำเร็จ: ${data.model}`, "success");
      } else {
        setGoogleResult(data.error || "ไม่สามารถเชื่อมต่อหรือทดสอบแปลได้", "error");
      }
    } catch (error) {
      setGoogleResult(error.message, "error");
    } finally {
      setGoogleBusy(false);
    }
  }

  async function saveGoogleConfig(event) {
    event.preventDefault();
    if (!googleEl.form.reportValidity()) return;
    setGoogleBusy(true);
    setGoogleResult("กำลังบันทึกการตั้งค่า Google Cloud Translation...", "info");
    try {
      const res = await fetch("/api/translation/google/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(googlePayload()),
      });
      if (!res.ok) throw new Error(await readError(res));
      const data = await res.json();
      googleEl.apiKey.value = "";
      googleEl.apiKeyHint.textContent = data.api_key_configured
        ? "มี API Key ตั้งค่าอยู่แล้ว — เว้นว่างเพื่อเก็บค่าเดิม"
        : "ยังไม่มี API Key — เว้นว่างได้หากใช้ Service Account";
      if (data.credentials_configured) {
        googleEl.credentialsHint.textContent = "✓ ตรวจพบไฟล์ Service Account JSON บนเครื่องแล้ว";
        googleEl.credentialsHint.style.color = "var(--color-success, #16a34a)";
        googleEl.status.className = "status-badge status-online";
        googleEl.status.textContent = "พร้อมใช้งาน (v3)";
      } else if (data.api_key_configured) {
        googleEl.credentialsHint.textContent = "พาธไฟล์ JSON ของ Google Cloud Service Account บนเครื่อง";
        googleEl.credentialsHint.style.color = "";
        googleEl.status.className = "status-badge status-online";
        googleEl.status.textContent = "พร้อมใช้งาน (v2)";
      } else {
        googleEl.status.className = "status-badge status-checking";
        googleEl.status.textContent = "ยังไม่ได้ตั้งค่า";
      }
      setGoogleResult("บันทึกการตั้งค่า Google Cloud Translation สำเร็จแล้ว", "success");
    } catch (error) {
      setGoogleResult(error.message, "error");
    } finally {
      setGoogleBusy(false);
    }
  }

  setTheme();
  el.transport.addEventListener("change", transportChanged);
  el.test.addEventListener("click", testConnection);
  el.form.addEventListener("submit", saveConfig);
  el.refreshCliStatus.addEventListener("click", () => loadCliStatus(true));

  if (googleEl.form) {
    googleEl.test.addEventListener("click", testGoogleConnection);
    googleEl.form.addEventListener("submit", saveGoogleConfig);
    loadGoogleConfig();
  }

  loadConfig();
  loadCliStatus();
})();
