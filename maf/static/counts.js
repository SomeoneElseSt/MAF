// Coming back to a list with Back or Forward, the browser shows the copy it kept from before, so the
// view and comment counts are from before you opened the post. Refresh each row's details line from
// the current page instead, in place (no reload, the scroll position stays).
(function () {
  async function refreshCounts() {
    const response = await fetch(location.href, { cache: "no-store", headers: { accept: "text/html" } });
    if (!response.ok) return;
    const fresh = new DOMParser().parseFromString(await response.text(), "text/html");
    for (const row of fresh.querySelectorAll("li[data-id]")) {
      const meta = row.querySelector(".meta");
      const shown = document.querySelector(`li[data-id="${CSS.escape(row.dataset.id)}"] .meta`);
      if (meta && shown) shown.innerHTML = meta.innerHTML;
    }
  }

  window.addEventListener("pageshow", event => {
    const returning = event.persisted || performance.getEntriesByType("navigation")[0]?.type === "back_forward";
    if (returning) refreshCounts().catch(() => {});
  });
})();
