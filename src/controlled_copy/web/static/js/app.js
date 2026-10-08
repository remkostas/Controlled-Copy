// Controlled Copy: small progressive enhancements on top of htmx.
// No inline scripts (strict CSP); everything here uses textContent, never innerHTML.
(function () {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const workspace = () => $(".workspace");

  // Printable page of a Studio output: print on open, and again from its button.
  document.addEventListener("click", (event) => {
    if (event.target.closest("[data-print]")) window.print();
  });

  // Print from the workspace without leaving it: the printable page loads in a hidden frame and
  // opens the print dialog itself. Without the script the link opens that page in a new tab.
  document.addEventListener("click", (event) => {
    const link = event.target.closest("a[data-print-frame]");
    if (!link) return;
    event.preventDefault();
    let frame = document.getElementById("print-frame");
    if (!frame) {
      frame = document.createElement("iframe");
      frame.id = "print-frame";
      frame.className = "print-frame";
      frame.title = "Print view";
      frame.setAttribute("aria-hidden", "true");
      frame.tabIndex = -1;
      document.body.append(frame);
    }
    frame.src = link.href;
  });
  document.addEventListener("DOMContentLoaded", () => {
    if (document.body.hasAttribute("data-autoprint")) window.setTimeout(() => window.print(), 300);
  });

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

  // Show or hide a typed access code. The button only appears when this script runs.
  document.addEventListener("click", (event) => {
    const toggle = event.target.closest("[data-reveal]");
    if (!toggle) return;
    const field = document.getElementById(toggle.dataset.reveal);
    if (!field) return;
    const show = field.type === "password";
    field.type = show ? "text" : "password";
    toggle.textContent = show ? "Hide" : "Show";
    toggle.setAttribute("aria-pressed", String(show));
    field.focus();
  });
  document.addEventListener("DOMContentLoaded", () => {
    $$("[data-reveal]").forEach((toggle) => (toggle.hidden = false));
  });

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
    // A citation shows its source even when the panel is collapsed (the stored choice stays).
    if (ws && ws.classList.contains("sources-collapsed")) setSourcesCollapsed(ws, false, false);
    if (ws) {
      withoutAnimation(ws, () => {
        ws.classList.add("is-reading");
        fitPanels(ws);
      });
    }
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
    if (ws) {
      withoutAnimation(ws, () => {
        ws.classList.remove("is-reading");
        fitPanels(ws);
      });
    }
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

  // A request that never reached the server (connection lost, the network changed) swaps
  // nothing, so say so instead of leaving the visitor in front of a page that does not change.
  // A typed question stays in the box, so pressing Enter again retries it.
  document.addEventListener("htmx:sendError", () => {
    toast("The connection was interrupted, so nothing was sent. Please try again.", false);
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
      const made = event.detail.xhr && event.detail.xhr.status < 300;
      const empty = $("#outputs-empty");
      if (empty) empty.remove();
      // Asked for from the chat: on the phone layout, show the Studio tab where it landed.
      const asker = event.detail.requestConfig && event.detail.requestConfig.elt;
      if (asker && asker.matches("[data-chat-summary]")) showTab("studio");
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
        // On a wide screen the new output also opens large over the chat, where it is seen at once.
        if (made && wideLayout()) openReader(outputs[0]);
      }
    }
  });

  // Reading view: a Studio output opens large over the chat, because the Studio column is narrow
  // and a new output is easy to miss below its buttons. The list in Studio keeps every output;
  // "Open" shows one again. Close, Escape or a citation (which opens its passage) return.
  function openReader(output) {
    const reader = $("#output-reader");
    const body = output && $(".output__body", output);
    if (!reader || !body) return;
    const text = (selector) => {
      const el = $(selector, output);
      return el ? el.textContent.trim() : "";
    };
    $(".reader__title", reader).textContent = text(".output__name");
    $(".reader__meta", reader).textContent = [text(".output__subject"), text(".output__meta")]
      .filter(Boolean)
      .join(" · ");
    const copy = body.cloneNode(true);
    $$("[id]", copy).forEach((el) => el.removeAttribute("id"));
    $$("[data-read-output]", copy).forEach((el) => el.remove());
    $(".reader__body", reader).replaceChildren(copy);
    if (window.htmx) window.htmx.process(copy);
    reader.hidden = false;
    showTab("chat");
    $(".reader__body", reader).scrollTop = 0;
    $("[data-reader-close]", reader).focus();
  }

  function closeReader() {
    const reader = $("#output-reader");
    if (!reader || reader.hidden) return;
    reader.hidden = true;
    $(".reader__body", reader).replaceChildren();
  }

  document.addEventListener("click", (event) => {
    const open = event.target.closest("[data-read-output]");
    if (open) {
      openReader(open.closest("details.output"));
      return;
    }
    if (event.target.closest("[data-reader-close]")) closeReader();
    // A citation opens its passage in the Sources panel; the chat comes back with it.
    else if (event.target.closest("#output-reader .cite")) closeReader();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !$("#viewer-slot [data-viewer]")) closeReader();
  });

  // Resizable side panels on wide layouts: drag the inner edge of Sources or Studio, or focus
  // it and use the arrow keys; double-click resets. The chat always keeps CHAT_MIN pixels.
  // Widths are a per-browser convenience, so storage failures are ignored.
  const WIDTHS_KEY = "cc-panel-widths";
  const SIDE_MIN = 224;
  const CHAT_MIN = 352;
  const KEY_STEP = 24;

  function storedWidths() {
    try {
      return JSON.parse(window.localStorage.getItem(WIDTHS_KEY)) || {};
    } catch (error) {
      return {};
    }
  }

  function storeWidth(name, width) {
    try {
      const widths = storedWidths();
      if (width === null) delete widths[name];
      else widths[name] = width;
      window.localStorage.setItem(WIDTHS_KEY, JSON.stringify(widths));
    } catch (error) {
      // Private window or blocked storage: the width still applies to this page.
    }
  }

  const wideLayout = () => !window.matchMedia("(max-width: 900px)").matches;
  const sidePanel = (ws, side) => $(side === "studio" ? ".panel--studio" : ".panel--sources", ws);
  const widthVar = (ws, side) =>
    side === "studio" ? "--col-studio" : ws.classList.contains("is-reading") ? "--col-reader" : "--col-sources";

  function setSideWidth(ws, side, wanted, remember) {
    const other = sidePanel(ws, side === "studio" ? "sources" : "studio");
    const max = Math.max(SIDE_MIN, ws.clientWidth - (other ? other.offsetWidth : 0) - CHAT_MIN);
    const width = Math.round(Math.min(Math.max(wanted, SIDE_MIN), max));
    const name = widthVar(ws, side);
    ws.style.setProperty(name, `${width}px`);
    if (remember) storeWidth(name, width);
    const handle = $(`[data-resize='${side}']`, ws);
    if (handle) {
      handle.setAttribute("aria-valuemin", String(SIDE_MIN));
      handle.setAttribute("aria-valuemax", String(max));
      handle.setAttribute("aria-valuenow", String(width));
    }
  }

  // Apply width changes without the column animation. The browser must compute the new
  // widths while "is-resizing" is still set; otherwise a style update after the class is
  // removed animates the change anyway (seen as a half-applied arrow-key step in CI).
  function withoutAnimation(ws, change) {
    ws.classList.add("is-resizing");
    change();
    void ws.offsetWidth; // flush styles now, with the animation off
    window.requestAnimationFrame(() => ws.classList.remove("is-resizing"));
  }

  // The width a panel is heading to: the set value, not the animated one mid-transition.
  function targetWidth(ws, side) {
    const set = parseFloat(ws.style.getPropertyValue(widthVar(ws, side)));
    return Number.isFinite(set) ? set : sidePanel(ws, side).offsetWidth;
  }

  function applyStoredWidths() {
    const ws = workspace();
    if (!ws || !wideLayout()) return;
    const widths = storedWidths();
    withoutAnimation(ws, () => {
      for (const name of ["--col-sources", "--col-reader", "--col-studio"]) {
        if (typeof widths[name] === "number") ws.style.setProperty(name, `${widths[name]}px`);
      }
      // Re-clamp for this window size without overwriting what was stored.
      for (const side of ["sources", "studio"]) {
        if (sidePanel(ws, side)) setSideWidth(ws, side, targetWidth(ws, side), false);
      }
      fitPanels(ws);
    });
  }

  // Keep the chat at least CHAT_MIN wide after anything that changes the side columns: opening
  // or closing a source (the Sources column switches between its own width and the reader's), a
  // restored width, or a narrower window. The Sources side gives way first, then Studio. Widths
  // set here are not stored, so the visitor's own choice comes back when there is room again.
  function fitPanels(ws) {
    if (!wideLayout()) return;
    const sources = sidePanel(ws, "sources");
    const studio = sidePanel(ws, "studio");
    if (!sources || !studio) return;
    const room = ws.clientWidth - CHAT_MIN;
    let left = sources.offsetWidth;
    let right = studio.offsetWidth;
    if (left + right <= room) return;
    if (!ws.classList.contains("sources-collapsed")) {
      left = Math.max(SIDE_MIN, room - right);
      ws.style.setProperty(widthVar(ws, "sources"), `${Math.round(left)}px`);
    }
    if (left + right > room) {
      right = Math.max(SIDE_MIN, room - left);
      ws.style.setProperty("--col-studio", `${Math.round(right)}px`);
    }
  }

  document.addEventListener("pointerdown", (event) => {
    const handle = event.target.closest("[data-resize]");
    const ws = workspace();
    if (!handle || !ws || !wideLayout()) return;
    event.preventDefault();
    const side = handle.dataset.resize;
    handle.setPointerCapture(event.pointerId);
    ws.classList.add("is-resizing");
    const move = (e) => {
      const box = ws.getBoundingClientRect();
      setSideWidth(ws, side, side === "studio" ? box.right - e.clientX : e.clientX - box.left, true);
    };
    const stop = () => {
      ws.classList.remove("is-resizing");
      handle.removeEventListener("pointermove", move);
      handle.removeEventListener("pointerup", stop);
      handle.removeEventListener("pointercancel", stop);
    };
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", stop);
    handle.addEventListener("pointercancel", stop);
  });

  document.addEventListener("keydown", (event) => {
    const handle = event.target.closest && event.target.closest("[data-resize]");
    const ws = workspace();
    if (!handle || !ws || !["ArrowLeft", "ArrowRight"].includes(event.key)) return;
    event.preventDefault();
    const side = handle.dataset.resize;
    // The arrow moves the edge: right widens Sources, left widens Studio.
    const grow = (event.key === "ArrowRight") === (side === "sources") ? KEY_STEP : -KEY_STEP;
    withoutAnimation(ws, () => setSideWidth(ws, side, targetWidth(ws, side) + grow, true));
  });

  document.addEventListener("dblclick", (event) => {
    const handle = event.target.closest("[data-resize]");
    const ws = workspace();
    if (!handle || !ws) return;
    const name = widthVar(ws, handle.dataset.resize);
    ws.style.removeProperty(name);
    storeWidth(name, null);
  });

  // Collapsible Sources panel on wide layouts, as in NotebookLM: more room for the chat and
  // Studio once the sources are picked. The choice is kept per browser.
  const COLLAPSE_KEY = "cc-sources-collapsed";

  function storedCollapsed() {
    try {
      return window.localStorage.getItem(COLLAPSE_KEY) === "1";
    } catch (error) {
      return false;
    }
  }

  function setSourcesCollapsed(ws, collapsed, remember) {
    ws.classList.toggle("sources-collapsed", collapsed);
    const button = $("[data-collapse='sources']", ws);
    if (button) {
      const label = collapsed ? "Show sources" : "Hide sources";
      button.setAttribute("aria-expanded", String(!collapsed));
      button.setAttribute("aria-label", label);
      button.title = label;
    }
    if (remember) {
      try {
        window.localStorage.setItem(COLLAPSE_KEY, collapsed ? "1" : "0");
      } catch (error) {
        // Private window or blocked storage: the choice still applies to this page.
      }
    }
  }

  function applyCollapsed() {
    const ws = workspace();
    if (!ws) return;
    const wanted = wideLayout() && storedCollapsed() && !ws.classList.contains("is-reading");
    if (wanted !== ws.classList.contains("sources-collapsed")) {
      withoutAnimation(ws, () => setSourcesCollapsed(ws, wanted, false));
    }
  }

  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-collapse='sources']");
    const ws = workspace();
    if (!button || !ws) return;
    setSourcesCollapsed(ws, !ws.classList.contains("sources-collapsed"), true);
  });

  let resizeTimer = 0;
  window.addEventListener("resize", () => {
    window.clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(() => {
      applyStoredWidths();
      applyCollapsed();
    }, 150);
  });

  document.addEventListener("DOMContentLoaded", () => {
    applyStoredWidths();
    applyCollapsed();
    updateSelectionCount();
    const box = $("#question");
    if (box) updateCounter(box);
    scrollChat();
  });
})();
