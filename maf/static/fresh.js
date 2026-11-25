// The front page, live: while you wait, "1 new post. Show?" appears when someone posts; Show reloads and
// scrolls to the New section, where the new post now is (new.js fills New).
(function () {
  const main = document.querySelector("main");
  if (!main) return;

  const SHOW_KEY = "maf.show-new"; // set by Show, so the reload scrolls to New
  const params = new URLSearchParams(window.location.search);

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
      // Storage off: Show still reloads, without the scroll.
    }
  }

  const postRows = scope => [...scope.querySelectorAll("li[data-id][data-created]")];

  if (read(sessionStorage, SHOW_KEY)) {
    write(sessionStorage, SHOW_KEY, null);
    try {
      history.scrollRestoration = "auto";
    } catch {
      // Older browsers: the scroll below still happens.
    }
    // After new.js (a later script) has filled New.
    const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    requestAnimationFrame(() => {
      const heading = document.getElementById("new-heading");
      if (heading && !heading.hidden) heading.scrollIntoView({ block: "start", behavior: calm ? "auto" : "smooth" });
    });
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
