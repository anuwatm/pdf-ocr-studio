(() => {
  "use strict";

  const el = {
    form: document.getElementById("llm-config-form"),
    baseUrl: document.getElementById("llm-base-url"),
    model: document.getElementById("llm-model"),
    apiKey: document.getElementById("llm-api-key"),
    apiKeyHint: document.getElementById("api-key-hint"),
    timeout: document.getElementById("llm-timeout"),
    test: document.getElementById("btn-test-connection"),
    save: document.getElementById("btn-save-config"),
    result: document.getElementById("config-result"),
    status: document.getElementById("config-status"),
    themeToggle: document.getElementById("btn-theme-toggle"),
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
      base_url: el.baseUrl.value.trim(),
      model: el.model.value.trim(),
      timeout: Number(el.timeout.value),
      api_key: key || null,
    };
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
      el.baseUrl.value = config.base_url;
      el.model.value = config.model;
      el.timeout.value = config.timeout;
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

  async function testConnection() {
    if (!el.form.reportValidity()) return;
    setBusy(true);
    setResult("กำลังทดสอบการเชื่อมต่อ Local LLM...", "info");
    try {
      const res = await fetch("/api/ai/config/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload()),
      });
      if (!res.ok) throw new Error(await readError(res));
      const data = await res.json();
      if (data.status === "connected") {
        setResult(`เชื่อมต่อสำเร็จ: ${data.configured_model}`, "success");
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

  setTheme();
  el.test.addEventListener("click", testConnection);
  el.form.addEventListener("submit", saveConfig);
  loadConfig();
})();
