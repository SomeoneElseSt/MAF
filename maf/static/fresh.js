// The front page, live: while you wait, "1 new post. Show?" appears when someone posts; Show reloads
// and scrolls to the first new post. On the plain front page, posts that arrived since this browser last
// showed it get a "New" label (gone on the next visit). The "last shown" time stays in this browser only.
(function () {
  const main = document.querySelector("main");
  if (!main) return;

  const SEEN_KEY = "maf.seen"; // created_at of the newest post this browser has shown on the front page
  const SHOW_KEY = "maf.show-new"; // set by Show, so the reload scrolls to the first new post
  const params = new URLSearchParams(window.location.search);
  const plainFrontPage = !params.has("tag") && !params.has("before") && !params.has("after");

  function read(storage, key) {
    try {
      return storage.getItem(key);
    } catch {
      return null;
    }
  }

  function write(storage, key, value) {
    try {
      if (value === null) storage.removeItem(key);
      else storage.setItem(key, value);
    } catch {
      // Storage off: no labels, everything else works.
    }
  }

  const postRows = scope => [...scope.querySelectorAll("li[data-id][data-created]")];

  // Created times are UTC ISO strings, so comparing them as text compares them as times.
  function labelNewPosts() {
    if (!plainFrontPage) return [];
    const seen = read(localStorage, SEEN_KEY);
    const rows = postRows(document);
    const fresh = seen ? rows.filter(row => row.dataset.created > seen) : [];
    for (const row of fresh) {
      const tag = document.createElement("span");
      tag.className = "new-tag";
      tag.textContent = "New";
      row.querySelector(".meta")?.append(tag);
    }
    const newest = rows.reduce((max, row) => (row.dataset.created > max ? row.dataset.created : max), seen || "");
    if (newest) write(localStorage, SEEN_KEY, newest);
    return fresh;
  }

  const fresh = labelNewPosts();
  if (read(sessionStorage, SHOW_KEY)) {
    write(sessionStorage, SHOW_KEY, null);
    try {
      history.scrollRestoration = "auto";
    } catch {
      // Older browsers: the scroll below still happens.
    }
    const first = fresh[0]?.querySelector(".title");
    const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (first) requestAnimationFrame(() => first.scrollIntoView({ block: "center", behavior: calm ? "auto" : "smooth" }));
  }

  if (!window.EventSource) return;
  let banner = null;

  function show() {
    write(sessionStorage, SHOW_KEY, "1");
    try {
      history.scrollRestoration = "manual";
    } catch {
      // A plain reload still works.
    }
    window.location.reload();
  }

  function showBanner(count) {
    if (!banner) {
      banner = document.createElement("div");
      banner.className = "notice live-replies";
      banner.setAttribute("role", "status");
      banner.innerHTML = '<p><span class="live-count"></span> <button class="live-show" type="button">Show</button>?</p>';
      banner.querySelector(".live-show").addEventListener("click", show);
      main.prepend(banner);
    }
    banner.querySelector(".live-count").textContent = `${count} new ${count === 1 ? "post" : "posts"}.`;
  }

  async function check() {
    const response = await fetch(window.location.pathname + window.location.search, { headers: { accept: "text/html" } });
    if (!response.ok) return;
    const page = new DOMParser().parseFromString(await response.text(), "text/html");
    const shown = new Set(postRows(document).map(row => row.dataset.id));
    const count = postRows(page).filter(row => !shown.has(row.dataset.id)).length;
    if (count) showBanner(count);
  }

  const source = new EventSource("/events");
  source.addEventListener("change", () => check().catch(() => {}));
  // After a reconnect (say, the site restarted), catch up on anything posted in between.
  let opened = false;
  source.addEventListener("open", () => {
    if (opened) check().catch(() => {});
    opened = true;
  });
})();
