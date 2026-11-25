// Reply opens a reply box under its comment (the mockup behaviour). Without JS the Reply link still opens it via :target.
(function () {
  function setOpen(link, form, open) {
    form.hidden = !open;
    link.setAttribute("aria-expanded", String(open));
    if (open) form.querySelector("textarea")?.focus();
  }

  function closeAll(except) {
    document.querySelectorAll(".reply-toggle:not([data-edit])[aria-expanded='true']").forEach(link => {
      if (link === except) return;
      setOpen(link, document.getElementById(link.getAttribute("aria-controls")), false);
    });
  }

  // Edit happens in place: the words (or the post body) are hidden and the box takes their place.
  // Cancel just unhides them, so what was there comes back exactly as it was.
  const editState = new Map();

  function openEdit(button) {
    const form = document.getElementById(button.dataset.edit);
    if (!form || !form.hidden) return;
    const target = form.previousElementSibling;
    if (!target || !target.classList.contains("text")) return;
    editState.set(form.id, { target });
    target.hidden = true;
    form.hidden = false;
    button.setAttribute("aria-expanded", "true");
    const box = form.querySelector("textarea");
    box.focus();
    box.selectionStart = box.selectionEnd = box.value.length;
  }

  function closeEdit(form) {
    const saved = editState.get(form.id);
    if (saved) saved.target.hidden = false;
    form.hidden = true;
    editState.delete(form.id);
    document.querySelector(`[data-edit="${CSS.escape(form.id)}"]`)?.setAttribute("aria-expanded", "false");
  }

  function markEdited(entryId) {
    // "(edited)" goes after the name and time, once.
    const meta = document.getElementById(entryId)?.querySelector(".meta");
    if (!meta || meta.querySelector(".edited")) return;
    const tag = document.createElement("span");
    tag.className = "edited";
    tag.textContent = "(edited)";
    const privateNote = meta.querySelector(".private-note");
    const anchor = privateNote ? privateNote.previousElementSibling : meta.lastChild;
    anchor.after(document.createTextNode(" "), tag);
  }

  document.querySelectorAll("[data-edit]").forEach(button => {
    button.addEventListener("click", () => openEdit(button));
  });

  document.querySelectorAll(".edit-in-place .cancel").forEach(cancel => {
    cancel.addEventListener("click", () => {
      const form = cancel.closest("form");
      closeEdit(form);
      document.querySelector(`[data-edit="${CSS.escape(form.id)}"]`)?.focus();
    });
  });

  // Edit buttons have their own handler above; this opens the boxes underneath.
  document.querySelectorAll(".reply-toggle:not([data-edit])").forEach(link => {
    const form = document.getElementById(link.getAttribute("aria-controls"));
    if (!form) return;
    link.addEventListener("click", event => {
      event.preventDefault();
      closeAll(link);
      setOpen(link, form, form.hidden);
    });
    if (form.classList.contains("edit-in-place")) return;
    form.querySelector(".cancel")?.addEventListener("click", event => {
      event.preventDefault();
      setOpen(link, form, false);
      link.focus();
    });
  });

  // Commenting, editing, deleting and flagging send in the background, then the page replaces itself
  // with the result. A normal form post adds a step to the browser's history, so Back would land on
  // this same thread first and need a second press. The server answers these with where to go.
  async function sendInPlace(form, submitter) {
    let response;
    try {
      response = await fetch(form.action, {
        method: "POST",
        body: new FormData(form, submitter), // includes the pressed button, e.g. Post anyway
        headers: { "X-MAF-In-Place": "1" },
      });
    } catch {
      form.dispatchEvent(new Event("maf:not-sent"));
      return;
    }
    const sentTo = response.headers.get("content-type")?.includes("application/json")
      ? (await response.json()).location
      : null;
    // Anything else (the name check's warning, a problem with the text) saved nothing: send it the
    // normal way so that page shows as it always has.
    if (!sentTo) {
      HTMLFormElement.prototype.submit.call(form);
      return;
    }
    const target = new URL(sentTo, location.href);
    const saved = !target.searchParams.has("notice");
    // An edit saved in place: show the saved words right there, no reload.
    if (saved && form.classList.contains("edit-in-place") && target.pathname === location.pathname) {
      showSavedEdit(form);
      return;
    }
    // Went through (no notice back): its draft is done, and the box is emptied so the reload doesn't refill it.
    if (saved) {
      form.dispatchEvent(new Event("maf:sent"));
      form.querySelectorAll("textarea").forEach(box => { box.value = ""; });
    }
    if (target.pathname !== location.pathname) {
      location.replace(target.href);
      return;
    }
    // Same thread: swap the address for this entry and reload. A reload keeps the old scroll position,
    // so the reply (#id) to land on is noted and scrolled to once the page is back.
    history.replaceState(history.state, "", target.pathname + target.search + target.hash);
    try {
      if (target.hash) sessionStorage.setItem(LAND_KEY, target.hash.slice(1));
    } catch {
      // Storage off: the page reloads where it was.
    }
    location.reload();
  }
  window.mafSendInPlace = sendInPlace;

  // The words as the server would render them: markdown for public edits, decrypted for private ones
  // (private.js seals before sending, so the box holds the plain text the person typed).
  function renderSaved(form) {
    const words = form.querySelector("textarea").value;
    const html = window.mafMarkdown?.(words);
    const text = document.createElement("div");
    text.className = "text";
    if (html) text.innerHTML = html;
    else text.textContent = words;
    return text;
  }

  function showSavedEdit(form) {
    const box = form.querySelector("textarea");
    const words = renderSaved(form);
    // The box keeps the saved words as its default, so opening Edit again, Cancel and the
    // reload reset all show them (not the empty value a reload would otherwise refill).
    box.defaultValue = box.value;
    form.dispatchEvent(new Event("maf:sent"));
    const shown = form.previousElementSibling;
    if (shown?.classList.contains("text")) {
      // Keep the element (and .post-body): only its words change.
      shown.innerHTML = words.innerHTML;
      if (form.hasAttribute("data-always-private")) shown.classList.add("open");
    } else {
      form.before(words);
    }
    const entry = form.closest("article, li");
    closeEdit(form);
    if (entry?.id) markEdited(entry.id);
    document.querySelector(`[data-edit="${CSS.escape(form.id)}"]`)?.focus();
  }

  const LAND_KEY = "maf.land-on";
  function landOnReply() {
    let id = null;
    try {
      id = sessionStorage.getItem(LAND_KEY);
      sessionStorage.removeItem(LAND_KEY);
    } catch {
      return;
    }
    const reply = id && document.getElementById(id);
    if (reply) reply.scrollIntoView({ block: "start" });
  }
  // After "load", so the browser's own scroll restore doesn't undo it.
  if (document.readyState === "complete") landOnReply();
  else window.addEventListener("load", () => requestAnimationFrame(landOnReply), { once: true });

  const IN_PLACE = "form[action='/comment'], form[action='/edit'], form[action='/delete-reply'], form[action='/flag']";
  document.addEventListener("submit", event => {
    const form = event.target.closest(IN_PLACE);
    if (!form || event.defaultPrevented) return;
    event.preventDefault();
    sendInPlace(form, event.submitter);
  });

  // The per-thread ID in a reply box opens the same pop-up as IDs elsewhere.
  document.querySelectorAll(".inline-reply .id").forEach(button => {
    button.addEventListener("click", () => document.getElementById("id-dialog")?.showModal());
  });
})();
