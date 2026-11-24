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

  // Flagging sends quietly and reloads in place: no new history entry, so Back still goes to the
  // page you came from, and the reload keeps your scroll position.
  document.addEventListener("submit", async event => {
    const form = event.target.closest("form[action='/flag']");
    if (!form) return;
    event.preventDefault();
    try {
      await fetch(form.action, { method: "POST", body: new FormData(form) });
    } finally {
      window.location.reload();
    }
  });

  // The per-thread ID in a reply box opens the same pop-up as IDs elsewhere.
  document.querySelectorAll(".inline-reply .id").forEach(button => {
    button.addEventListener("click", () => document.getElementById("id-dialog")?.showModal());
  });
})();
