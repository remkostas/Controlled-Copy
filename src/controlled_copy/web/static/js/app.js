// Controlled Copy: small progressive enhancements on top of htmx.
// No inline scripts (strict CSP); everything here uses textContent, never innerHTML.
(function () {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const workspace = () => $(".workspace");

  // Notebook switcher submits on change.
  document.addEventListener("change", (event) => {
    const el = event.target;
    if (el.matches("select[data-autosubmit]")) el.form.submit();
    if (el.matches("input[data-select-all]")) {
      $$("input[name='source_ids']").forEach((box) => (box.checked = el.checked));
      updateSelectionCount();
    }
    if (el.matches("input[name='source_ids']")) updateSelectionCount();
    if (el.matches("select[data-fill-target]") && el.value) {
      const target = document.getElementById(el.dataset.fillTarget);
      if (target) {
        target.value = el.value;
        if (target.dataset.counter) updateCounter(target);
      }
    }
  });

  function updateSelectionCount() {
    const boxes = $$("input[name='source_ids']");
    const checked = boxes.filter((b) => b.checked).length;
    const all = $("input[data-select-all]");
    if (all) {
      all.checked = checked === boxes.length && boxes.length > 0;
      all.indeterminate = checked > 0 && checked < boxes.length;
      const count = all.parentElement.querySelector(".mono");
      if (count) count.textContent = `(${checked}/${boxes.length})`;
    }
  }

  // Disclosure buttons (paste form, new notebook).
  document.addEventListener("click", (event) => {
    const toggle = event.target.closest("[data-toggle]");
    if (toggle) {
      const target = document.getElementById(toggle.dataset.toggle);
      if (!target) return;
      const open = target.hidden;
      target.hidden = !open;
      toggle.setAttribute("aria-expanded", String(open));
      if (open) {
        const first = target.querySelector("input, textarea");
        if (first) first.focus();
      }
      return;
    }

    const suggestion = event.target.closest(".suggestion");
    if (suggestion) {
      const box = $("#question");
      if (!box || box.disabled) return;
      box.value = suggestion.dataset.question || "";
      updateCounter(box);
      $("#ask-form").requestSubmit();
      return;
    }

    if (event.target.closest("[data-close-viewer]")) {
      closeViewer();
      return;
    }

    const copy = event.target.closest("[data-copy-markdown]");
    if (copy) {
      copyMarkdown(copy);
      return;
    }

    const tab = event.target.closest(".mobile-tabs [data-tab]");
    if (tab) showTab(tab.dataset.tab);
  });

  // "Copy as Markdown": fetch the visitor's own export and put it on the clipboard.
  function toast(message, ok) {
    const box = $("#toast");
    if (!box) return;
    const note = document.createElement("p");
    note.className = ok ? "notice" : "notice notice--error";
    note.setAttribute("role", ok ? "status" : "alert");
    note.textContent = message;
    box.replaceChildren(note);
    window.setTimeout(() => box.replaceChildren(), 8000);
  }

  async function copyMarkdown(button) {
    try {
      const response = await fetch(button.dataset.copyMarkdown, { credentials: "same-origin" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      await navigator.clipboard.writeText(await response.text());
      toast("Copied as Markdown.", true);
    } catch (error) {
      toast("Copying did not work in this browser. Use Download .md instead.", false);
    }
  }

  function showTab(name) {
    const ws = workspace();
    if (!ws) return;
    ws.dataset.tab = name;
    $$(".mobile-tabs [data-tab]").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === name)));
  }

  // Source viewer: replaces the source list inside the Sources panel.
  function openViewer() {
    const ws = workspace();
    const browser = $("#source-browser");
    const widening = Boolean(ws) && !ws.classList.contains("is-reading");
    if (ws) ws.classList.add("is-reading");
    if (browser) browser.hidden = true;
    showTab("sources");
    const cited = $("#cited");
    const panelBody = $("#sources-panel .panel__body");
    if (!cited) {
      if (panelBody) panelBody.scrollTop = 0;
      return;
    }
    const center = () => cited.scrollIntoView({ block: "center" });
    center();
    // The reading column widens with an animation and the text reflows while it does, which
    // moves the passage: centre it again once the column has its final width.
    if (widening) {
      let done = false;
      const settle = () => {
        if (done) return;
        done = true;
        ws.removeEventListener("transitionend", onEnd);
        center();
      };
      // Only the column animation counts: transitions of children (a hover colour) bubble here too.
      const onEnd = (event) => {
        if (event.target === ws && event.propertyName === "grid-template-columns") settle();
      };
      ws.addEventListener("transitionend", onEnd);
      setTimeout(settle, 400);
    }
  }

  function closeViewer() {
    const slot = $("#viewer-slot");
    if (slot) slot.replaceChildren();
    const ws = workspace();
    if (ws) ws.classList.remove("is-reading");
    const browser = $("#source-browser");
    if (browser) browser.hidden = false;
    $$(".cite[aria-current]").forEach((c) => c.removeAttribute("aria-current"));
  }

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && $("#viewer-slot [data-viewer]")) closeViewer();
    const box = event.target;
    if (box.id === "question" && event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      if (box.value.trim()) $("#ask-form").requestSubmit();
    }
  });

  // Character counter.
  function updateCounter(box) {
    const counter = document.getElementById(box.dataset.counter);
    if (!counter) return;
    const max = Number(counter.dataset.max);
    counter.textContent = `${box.value.length.toLocaleString("en")} / ${max.toLocaleString("en")}`;
    counter.classList.toggle("is-over", box.value.length > max);
    box.style.height = "auto";
    box.style.height = `${Math.min(box.scrollHeight, 160)}px`;
  }
  document.addEventListener("input", (event) => {
    if (event.target.dataset && event.target.dataset.counter) updateCounter(event.target);
  });

  function scrollChat() {
    const log = $("#chat-log");
    if (log) log.scrollTop = log.scrollHeight;
  }

  // htmx lifecycle hooks.
  document.addEventListener("htmx:beforeRequest", (event) => {
    const form = event.detail.elt;
    if (form && form.id === "ask-form") {
      const pending = $("#pending-turn");
      const box = $("#question");
      if (pending && box) {
        $("[data-pending-question]", pending).textContent = box.value;
        pending.hidden = false;
        scrollChat();
      }
    }
    const cite = event.target.closest && event.target.closest(".cite");
    if (cite) {
      $$(".cite[aria-current]").forEach((c) => c.removeAttribute("aria-current"));
      cite.setAttribute("aria-current", "true");
    }
  });

  document.addEventListener("htmx:afterRequest", (event) => {
    const elt = event.detail.elt;
    if (elt && elt.id === "ask-form") {
      const pending = $("#pending-turn");
      if (pending) pending.hidden = true;
      if (event.detail.successful) {
        const box = $("#question");
        box.value = "";
        updateCounter(box);
        const suggestions = $("#suggestions");
        if (suggestions) suggestions.remove();
      }
      scrollChat();
    }
    if (elt && elt.matches && elt.matches("form.file-pick")) {
      const input = $("input[type='file']", elt);
      if (input) input.value = "";
    }
    if (elt && elt.id === "paste-form" && event.detail.successful) {
      elt.reset();
      elt.hidden = true;
      const toggle = $("[data-toggle='paste-form']");
      if (toggle) toggle.setAttribute("aria-expanded", "false");
    }
  });

  document.addEventListener("htmx:afterSwap", (event) => {
    const target = event.detail.target;
    if (!target) return;
    if (target.id === "viewer-slot" && $("[data-viewer]", target)) openViewer();
    if (target.id === "source-list-wrap") {
      updateSelectionCount();
      const status = $("#add-source-status");
      if (status && event.detail.xhr && event.detail.xhr.status < 300) status.replaceChildren();
      // Typed document-control fields apply to one upload only.
      if (event.detail.xhr && event.detail.xhr.status < 300) {
        $$("#doc-control input, #doc-control select").forEach((field) => (field.value = ""));
      }
    }
    // The first answer makes a chat to start over from: show New chat without a reload.
    if (target.id === "pending-turn" && event.detail.xhr && event.detail.xhr.status < 300) {
      const newChat = $("#new-chat");
      if (newChat) newChat.hidden = false;
    }
    if (target.id === "toast") {
      window.setTimeout(() => target.replaceChildren(), 8000);
    }
    if (target.id === "studio-outputs") {
      const empty = $("#outputs-empty");
      if (empty) empty.remove();
      // A new output arrives at the top: keep only it open and bring it into view, so it is
      // clear what was just made and an older output is not read by mistake.
      const outputs = $$("details.output", target);
      if (outputs.length) {
        outputs.forEach((output, index) => (output.open = index === 0));
        // Scroll only the Studio panel, never the page (it is locked to the window).
        const panel = target.closest(".panel__body");
        if (panel) {
          panel.scrollTop += outputs[0].getBoundingClientRect().top - panel.getBoundingClientRect().top;
        }
      }
    }
  });

  document.addEventListener("DOMContentLoaded", () => {
    updateSelectionCount();
    const box = $("#question");
    if (box) updateCounter(box);
    scrollChat();
  });
})();
