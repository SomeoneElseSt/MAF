// View and comment counts on a list, right when you come back to it with Back or Forward.
// The browser shows a copy of the list from earlier (sometimes from before you opened any post), so its
// counts are old. This tab remembers the newest counts it has seen: from each list it loads, from each
// post you open (which includes your own view), and from refreshing the list in the background. Coming
// back, those go in at once, so a count never dips and then jumps; the background refresh then
// fills in everyone else's views and comments. Only the counts change, so the "New" labels stay.
(function () {
  const KEY = "maf.counts"; // {post id: {views, comments}}, kept for this tab only

  function remembered() {
    try {
      return JSON.parse(sessionStorage.getItem(KEY) || "{}");
    } catch {
      return {};
    }
  }

  function remember(entries) {
    try {
      sessionStorage.setItem(KEY, JSON.stringify({ ...remembered(), ...entries }));
    } catch {
      // Storage off: the background refresh still fixes the counts, a moment later.
    }
  }

  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
  const numberIn = (text, pattern) => Number(text.match(pattern)?.[1] ?? 0);
  const countsOf = text => ({ comments: numberIn(text, /(\d+) comments?/), views: numberIn(text, /(\d+) views?/) });
  const withCounts = (text, counts) =>
    text.replace(/\d+ comments?/, plural(counts.comments, "comment")).replace(/\d+ views?/, plural(counts.views, "view"));

  const returning = performance.getEntriesByType("navigation")[0]?.type === "back_forward";

  // A post: note its counts, unless this is itself an old copy brought back by Back or Forward.
  const post = document.querySelector("article.post-head[data-views]");
  if (post) {
    if (!returning) remember({ [post.id]: { views: Number(post.dataset.views), comments: Number(post.dataset.comments) } });
    return;
  }

  const shownCounts = () => [...document.querySelectorAll("li[data-id] .counts")];
  const rowId = counts => counts.closest("li[data-id]").dataset.id;

  function showRemembered() {
    const newest = remembered();
    for (const counts of shownCounts()) {
      const known = newest[rowId(counts)];
      if (known) counts.textContent = withCounts(counts.textContent, known);
    }
  }

  function rememberShown(scope) {
    const entries = {};
    for (const counts of scope.querySelectorAll("li[data-id] .counts")) entries[rowId(counts)] = countsOf(counts.textContent);
    remember(entries);
  }

  async function refreshCounts() {
    const response = await fetch(location.href, { cache: "no-store", headers: { accept: "text/html" } });
    if (!response.ok) return;
    const fresh = new DOMParser().parseFromString(await response.text(), "text/html");
    rememberShown(fresh);
    for (const counts of fresh.querySelectorAll("li[data-id] .counts")) {
      const shown = document.querySelector(`li[data-id="${CSS.escape(rowId(counts))}"] .counts`);
      if (shown) shown.textContent = counts.textContent;
    }
  }

  // Runs before the page is first drawn: an old copy never shows its old counts.
  if (returning) showRemembered();
  else rememberShown(document);

  window.addEventListener("pageshow", event => {
    if (!event.persisted && !returning) return;
    if (event.persisted) showRemembered();
    refreshCounts().catch(() => {});
  });
})();
