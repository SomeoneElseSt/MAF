// The front page, live: while you wait, "1 new post. Show?" appears when someone posts; Show reloads
// and scrolls to the first new post. On the plain front page, posts that arrived since this browser last
// showed it get a "New" label, and posts with comments newer than the last visit get "New comments"
// (both gone on the next visit). Those times stay in this browser only.
(function () {
  const main = document.querySelector("main");
  if (!main) return;

  const SEEN_KEY = "maf.seen"; // created_at of the newest post this browser has shown on the front page
  const COMMENTS_KEY = "maf.comments-seen"; // when this browser last looked at the front page, for "New comments" 
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
  // Coming back with Back or Forward is the same visit: the page shows the labels it showed before,
  // from the times kept with this history entry, even when the browser loads it again.
  function lastVisit() {
    const returning = performance.getEntriesByType("navigation")[0]?.type === "back_forward";
    const kept = returning ? history.state?.mafLastVisit : null;
    if (kept) return kept;
    const visit = { seen: read(localStorage, SEEN_KEY), comments: read(localStorage, COMMENTS_KEY) };
    try {
      history.replaceState({ ...history.state, mafLastVisit: visit }, "");
    } catch {
      // No history state: a reload by Back counts as a new visit.
    }
    return visit;
  }

  function labelNewPosts() {
    if (!plainFrontPage) return [];
    const visit = lastVisit();
    const seen = visit.seen;
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
    labelNewComments(rows, visit.comments);
    write(localStorage, COMMENTS_KEY, new Date().toISOString());
    return fresh;
  }

  // A post whose newest comment came after the last visit gets "New comments". Posts already
  // labelled "New" don't need it: everything about them is new.
  function labelNewComments(rows, since) {
    if (!since) return;
    for (const row of rows) {
      const latest = row.dataset.latestComment;
      if (!latest || latest <= since || row.querySelector(".new-tag")) continue;
      const tag = document.createElement("span");
      tag.className = "new-tag";
      tag.textContent = "New comments";
      row.querySelector(".meta")?.append(tag);
    }
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

  // New posts only ever show up on the latest dates or the first page of a hashtag.
  const latestPage = !params.has("before") && !params.has("after") && !(Number(params.get("page")) > 1);
  if (!window.EventSource || !latestPage) return;
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
      const sortRow = document.querySelector(".listbar");
      if (sortRow) sortRow.after(banner);
      else main.prepend(banner);
    }
    banner.querySelector(".live-count").textContent = `${count} new ${count === 1 ? "post" : "posts"}.`;
  }

  async function check() {
    const response = await fetch(window.location.pathname + window.location.search, { headers: { accept: "text/html" } });
    if (!response.ok) return;
    const page = new DOMParser().parseFromString(await response.text(), "text/html");
    // Only posts newer than the newest one on screen: not ones that are merely missing from it.
    const rows = postRows(document);
    const shown = new Set(rows.map(row => row.dataset.id));
    const newest = rows.reduce((max, row) => (row.dataset.created > max ? row.dataset.created : max), "");
    const count = postRows(page).filter(row => !shown.has(row.dataset.id) && row.dataset.created > newest).length;
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
