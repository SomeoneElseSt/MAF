// Reply opens a reply box under its comment (the mockup behaviour). Without JS the Reply link still opens it via :target.
(function () {
  function setOpen(link, form, open) {
    form.hidden = !open;
    link.setAttribute("aria-expanded", String(open));
    if (open) form.querySelector("textarea")?.focus();
  }

  function closeAll(except) {
    document.querySelectorAll(".reply-toggle[aria-expanded='true']").forEach(link => {
      if (link === except) return;
      setOpen(link, document.getElementById(link.getAttribute("aria-controls")), false);
    });
  }

  document.querySelectorAll(".reply-toggle").forEach(link => {
    const form = document.getElementById(link.getAttribute("aria-controls"));
    if (!form) return;
    link.addEventListener("click", event => {
      event.preventDefault();
      closeAll(link);
      setOpen(link, form, form.hidden);
    });
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
    // Went through (no notice back): its draft is done, and the box is emptied so the reload doesn't refill it.
    if (!target.searchParams.has("notice")) {
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
