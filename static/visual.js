"use strict";

// The editable document is isolated from the application; scripts remain disabled.
window.createVisualEditor = ({getValue, onChange, onSave, canEdit}) => {
  const frame = document.getElementById("html-visual-frame");
  const toolbar = document.getElementById("html-visual-toolbar");
  const allowedTags = new Set(["P", "H1", "H2", "H3", "B", "I", "STRONG", "EM", "U", "S", "SPAN", "BR", "SECTION", "MAIN", "DIV", "UL", "OL", "LI", "A", "BLOCKQUOTE", "TABLE", "THEAD", "TBODY", "TFOOT", "TR", "TH", "TD", "CAPTION"]);
  const discardTags = new Set(["SCRIPT", "STYLE", "IFRAME", "OBJECT", "SVG", "MATH", "APPLET", "FORM", "BUTTON", "TEXTAREA", "SELECT", "TEMPLATE"]);
  const allowedAttrs = new Set(["id", "class", "data-page", "data-src", "data-edited", "data-block-id", "data-cell-id", "data-bbox", "lang", "rowspan", "colspan"]);
  let sourceDocument;
  let selectionRange;
  let loadedValue;
  let ready = false;

  function safeLink(value) {
    const url = value.trim();
    if (/[\u0000-\u0020\u007f]/.test(url)) return null;
    if (url.startsWith("#")) return url;
    try {
      const parsed = new URL(url);
      return ["http:", "https:", "mailto:"].includes(parsed.protocol) ? url : null;
    } catch { return null; }
  }

  function cleanBody(body) {
    for (const node of [...body.querySelectorAll("*")]) {
      if (!body.contains(node)) continue;
      if (discardTags.has(node.tagName)) { node.remove(); continue; }
      if (!allowedTags.has(node.tagName)) { node.replaceWith(...node.childNodes); continue; }
      for (const attr of [...node.attributes]) {
        if (node.tagName === "A" && attr.name === "href" && safeLink(attr.value)) continue;
        if (!allowedAttrs.has(attr.name)) node.removeAttribute(attr.name);
      }
    }
  }

  function sync() {
    if (!ready || !canEdit()) return;
    const body = frame.contentDocument.body.cloneNode(true);
    cleanBody(body);
    sourceDocument.body.innerHTML = body.innerHTML;
    loadedValue = "<!doctype html>\n" + sourceDocument.documentElement.outerHTML;
    onChange(loadedValue);
    updateToolbar();
  }

  function updateToolbar() {
    const doc = frame.contentDocument;
    const block = ready ? doc.queryCommandValue("formatBlock").toLowerCase().replace(/[<>]/g, "") : "p";
    document.getElementById("visual-block-format").value = ["p", "h1", "h2", "h3"].includes(block) ? block : "p";
    for (const button of toolbar.querySelectorAll("[data-visual-command]")) {
      const command = button.dataset.visualCommand;
      if (["bold", "italic", "underline", "insertUnorderedList", "insertOrderedList"].includes(command)) {
        button.setAttribute("aria-pressed", String(Boolean(ready && doc.queryCommandState(command))));
      }
    }
  }

  function restoreSelection() {
    frame.contentWindow.focus();
    if (selectionRange && frame.contentDocument.body.contains(selectionRange.commonAncestorContainer)) {
      const selection = frame.contentWindow.getSelection();
      selection.removeAllRanges();
      selection.addRange(selectionRange);
    }
  }

  function command(name, value = null) {
    if (!ready || !canEdit()) return;
    restoreSelection();
    // Native editing commands retain the browser's undo history in Edge/Chrome.
    frame.contentDocument.execCommand(name, false, value);
    sync();
  }

  function addLink() {
    if (!ready || !canEdit()) return;
    restoreSelection();
    if (frame.contentWindow.getSelection().isCollapsed) {
      alert("เลือกข้อความที่ต้องการทำเป็นลิงก์ก่อน"); return;
    }
    const input = prompt("URL ของลิงก์ (https://, http://, mailto: หรือ #หัวข้อ)", "https://");
    if (input === null) return;
    const url = safeLink(input);
    if (!url) { alert("URL ไม่ถูกต้อง รองรับ http://, https://, mailto: และ #หัวข้อ"); return; }
    command("createLink", url);
  }

  frame.addEventListener("load", () => {
    const doc = frame.contentDocument;
    if (!sourceDocument || !doc?.body || doc.body.dataset.visualDocument !== "ready") return;
    ready = true;
    doc.body.removeAttribute("data-visual-document");
    doc.body.contentEditable = canEdit() ? "true" : "false";
    doc.body.setAttribute("role", "textbox");
    doc.body.setAttribute("aria-label", "แก้ไขเนื้อหา HTML แบบ Word");
    doc.body.setAttribute("aria-multiline", "true");
    doc.execCommand("styleWithCSS", false, false);
    doc.execCommand("defaultParagraphSeparator", false, "p");
    doc.addEventListener("input", sync);
    doc.addEventListener("selectionchange", () => {
      const selection = doc.getSelection();
      if (selection.rangeCount) selectionRange = selection.getRangeAt(0).cloneRange();
      updateToolbar();
    });
    doc.addEventListener("click", event => {
      if (event.target.closest("a")) event.preventDefault();
    });
    doc.addEventListener("keydown", event => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
        event.preventDefault(); sync(); onSave();
      }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault(); addLink();
      }
    });
    doc.addEventListener("paste", event => {
      event.preventDefault();
      command("insertText", event.clipboardData.getData("text/plain"));
    });
    doc.addEventListener("drop", event => event.preventDefault());
    updateToolbar();
  });

  function load() {
    const value = getValue();
    if (value === loadedValue && ready) {
      frame.contentDocument.body.contentEditable = canEdit() ? "true" : "false";
      return;
    }
    ready = false;
    loadedValue = value;
    selectionRange = null;
    sourceDocument = new DOMParser().parseFromString(value, "text/html");
    const doc = sourceDocument.cloneNode(true);
    cleanBody(doc.body);
    // Rebuild the editor head: no external resources or document-provided policies.
    const styles = [...doc.head.querySelectorAll("style")].map(node => node.textContent);
    doc.head.replaceChildren();
    const policy = doc.createElement("meta");
    policy.httpEquiv = "Content-Security-Policy";
    policy.content = "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'";
    doc.head.append(policy);
    const style = doc.createElement("style");
    style.textContent = styles.join("\n") + "\nhtml{background:white;color:#172033}body{padding:24px;margin:0;min-height:80vh;outline:none;font:18px/1.7 Tahoma,sans-serif;overflow-wrap:anywhere}a{color:#2563eb;text-decoration:underline}";
    doc.head.append(style);
    for (const attr of [...doc.documentElement.attributes]) doc.documentElement.removeAttribute(attr.name);
    for (const attr of [...doc.body.attributes]) doc.body.removeAttribute(attr.name);
    doc.body.dataset.visualDocument = "ready";
    frame.srcdoc = "<!doctype html>" + doc.documentElement.outerHTML;
  }

  toolbar.addEventListener("mousedown", event => {
    if (event.target.closest("button")) event.preventDefault();
  });
  toolbar.querySelectorAll("[data-visual-command]").forEach(button => {
    button.addEventListener("click", () => command(button.dataset.visualCommand));
  });
  document.getElementById("visual-block-format").addEventListener("change", event => command("formatBlock", event.target.value));
  document.getElementById("visual-link").addEventListener("click", addLink);
  return {load};
};
