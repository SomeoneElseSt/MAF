// Coming back to a list with Back or Forward, the browser may show the page as you left it, so the
// view and comment counts are from before you opened the post. Refresh each row's counts from the
// current page instead, in place (no reload, the scroll position stays). Only the counts change,
// so the "New" labels stay.
(function () {
  async function refreshCounts() {
    const response = await fetch(location.href, { cache: "no-store", headers: { accept: "text/html" } });
    if (!response.ok) return;
    const fresh = new DOMParser().parseFromString(await response.text(), "text/html");
    for (const row of fresh.querySelectorAll("li[data-id]")) {
      const counts = row.querySelector(".counts");
      const shown = document.querySelector(`li[data-id="${CSS.escape(row.dataset.id)}"] .counts`);
      if (counts && shown) shown.textContent = counts.textContent;
    }
  }

  window.addEventListener("pageshow", event => {
    const returning = event.persisted || performance.getEntriesByType("navigation")[0]?.type === "back_forward";
    if (returning) refreshCounts().catch(() => {});
  });
})();
