// Up and down votes on a post, on the thread page. Each arrow is already a small form (POST /vote);
// this sends it without reloading, then swaps in the vote box from the page the server answers with,
// so the score and the filled arrow come from the server, not a guess. Like reactions.js, it adds no
// history entry, and anything unexpected (signed out, slowed down) loads the answer page instead.
(function () {
  async function send(form) {
    const box = form.closest(".vote");
    try {
      const response = await fetch(form.action, { method: "POST", body: new FormData(form) });
      const url = new URL(response.url);
      const fresh = response.ok && !url.searchParams.has("notice") && url.pathname === window.location.pathname
        ? new DOMParser().parseFromString(await response.text(), "text/html")
            .querySelector(`.vote[data-item="${CSS.escape(box.dataset.item)}"]`)
        : null;
      if (!fresh) {
        window.location.replace(response.url);
        return;
      }
      box.replaceWith(document.adoptNode(fresh));
      fresh.querySelector(`.${form.querySelector("button").className}`)?.focus({ preventScroll: true });
    } catch {
      window.location.replace(window.location.href);
    }
  }

  // Delegated, so a box that was just swapped in keeps working.
  document.addEventListener("submit", event => {
    const form = event.target.closest(".vote-form");
    if (!form) return;
    event.preventDefault();
    send(form);
  });
})();
