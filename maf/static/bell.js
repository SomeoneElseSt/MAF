// The "Feed" link in the header (the notification bell): a count of new replies to your posts and replies, and new reactions on them.
// Clicking opens the list; each row goes to the reply or post it's about. What you've already seen is
// remembered in this browser only (the time of the newest thing you've seen), so the server keeps no
// record of when you check. Updates live when someone replies or reacts.
(function () {
  const bell = document.querySelector(".bell");
  const menu = document.getElementById("bell-menu");
  const badge = bell?.querySelector(".bell-count");
  if (!bell || !menu || !badge) return;

  const SEEN_KEY = "maf.bell-seen";
  const COUNT_KEY = "maf.bell-count"; // the last count shown, so a new page starts with it instead of flashing
  const MAX_SHOWN_COUNT = 99;
  let items = [];

  function readSeen() {
    try {
      return localStorage.getItem(SEEN_KEY);
    } catch {
      return null;
    }
  }

  function writeSeen(value) {
    try {
      localStorage.setItem(SEEN_KEY, value);
    } catch {
      // Storage off: the count resets on every page.
    }
  }

  // The first time, start from now rather than counting everything that ever happened.
  if (!readSeen()) writeSeen(new Date().toISOString().replace(/\.\d+Z$/, "Z"));

  // Times are UTC ISO strings, so comparing them as text compares them as times.
  const newTimes = item => item.times.filter(time => time > readSeen());
  const isNew = item => newTimes(item).length > 0;

  function plural(n, word) {
    return `${n} ${word}${n === 1 ? "" : "s"}`;
  }

  function ago(iso) {
    const seconds = Math.max(0, (Date.now() - Date.parse(iso)) / 1000);
    if (seconds < 60) return "just now";
    if (seconds < 3600) return `${plural(Math.floor(seconds / 60), "minute")} ago`;
    if (seconds < 86400) return `${plural(Math.floor(seconds / 3600), "hour")} ago`;
    const days = Math.floor(seconds / 86400);
    return days === 1 ? "Yesterday" : `${days} days ago`;
  }

  function paint(count) {
    badge.textContent = count > MAX_SHOWN_COUNT ? `${MAX_SHOWN_COUNT}+` : String(count);
    bell.classList.toggle("has-new", count > 0);
  }

  function showCount() {
    const count = items.reduce((sum, item) => sum + newTimes(item).length, 0);
    paint(count);
    try {
      sessionStorage.setItem(COUNT_KEY, String(count));
    } catch {
      // Storage off: the next page starts at 0 until the count loads.
    }
    bell.setAttribute("aria-label", count ? `Feed: replies and reactions, ${count} new` : "Feed: replies and reactions");
  }

  // A row for the page you're already on would only change the #part, which adds a step to history
  // (so Back lands on this same page instead of where you came from). Replace the current entry and
  // reload instead, which also brings in the new reply.
  function follow(event, url) {
    const target = new URL(url, location.href);
    if (target.pathname !== location.pathname) return;
    event.preventDefault();
    history.replaceState(history.state, "", target.pathname + target.search + target.hash);
    location.reload();
  }

  function row(item) {
    const link = document.createElement("a");
    link.href = item.url;
    link.className = "bell-item";
    link.addEventListener("click", event => follow(event, item.url));
    const what = document.createElement("span");
    what.className = "bell-what";
    what.textContent = item.label; // worded by the server (store.notifications), same as the Feed page
    if (isNew(item)) {
      const tag = document.createElement("span");
      tag.className = "new-tag";
      tag.textContent = "New";
      what.append(tag);
    }
    const meta = document.createElement("span");
    meta.className = "bell-meta";
    meta.textContent = `“${item.about}”, ${ago(item.at)}`;
    link.append(what, meta);
    return link;
  }

  function render() {
    if (!items.length) {
      const empty = document.createElement("p");
      empty.className = "bell-empty";
      empty.textContent = "Replies and reactions to your posts and comments show up here.";
      menu.replaceChildren(empty);
      rendered();
      return;
    }
    // Scrolls like the # menu: no scrollbar, faded edges, and chevrons where there's more (from tags.js).
    const scroller = Object.assign(document.createElement("div"), { className: "tag-scroll" });
    scroller.append(...items.map(row));
    scroller.addEventListener("scroll", () => updateTagFade(menu));
    // The chevrons float over the list itself, so the alerts line below it (alerts.js) stays clear of them.
    const list = Object.assign(document.createElement("div"), { className: "bell-list" });
    list.append(scrollArrow("up", scroller), scroller, scrollArrow("down", scroller));
    menu.replaceChildren(list);
    requestAnimationFrame(() => updateTagFade(menu));
    rendered();
  }

  // alerts.js adds its line (alerts on this device, and turning them off) to the bottom of the menu.
  function rendered() {
    document.dispatchEvent(new CustomEvent("maf:feed-menu", { detail: menu }));
  }

  async function load() {
    const response = await fetch("/notifications.json", { headers: { accept: "application/json" } });
    if (!response.ok) return;
    items = (await response.json()).items;
    showCount();
    if (!menu.hidden) render();
  }

  // Centred under "Feed", but never past the window edge (16px gutter), whatever the window width.
  const GUTTER = 16;
  function keepOnScreen() {
    menu.style.transform = "";
    const box = menu.getBoundingClientRect();
    const room = document.documentElement.clientWidth - GUTTER;
    const shift = box.right > room ? room - box.right : Math.max(0, GUTTER - box.left);
    if (shift) menu.style.transform = `translateX(calc(-50% + ${shift}px))`;
  }

  function close() {
    menu.hidden = true;
    bell.setAttribute("aria-expanded", "false");
  }

  // Opening shows what's new (marked "New"), then counts it all as seen.
  function open() {
    render();
    menu.hidden = false;
    keepOnScreen();
    bell.setAttribute("aria-expanded", "true");
    const newest = items.reduce((max, item) => (item.at > max ? item.at : max), readSeen());
    writeSeen(newest);
    showCount();
  }

  bell.addEventListener("click", event => {
    event.preventDefault();
    if (menu.hidden) open();
    else close();
  });
  document.addEventListener("click", event => {
    if (!menu.hidden && !event.target.closest(".bell-wrap")) close();
  });
  window.addEventListener("resize", () => {
    if (!menu.hidden) keepOnScreen();
  });
  document.addEventListener("keydown", event => {
    if (event.key !== "Escape" || menu.hidden) return;
    close();
    bell.focus();
  });

  let lastCount = 0;
  try {
    lastCount = Number(sessionStorage.getItem(COUNT_KEY)) || 0;
  } catch {
    // Storage off: start at 0.
  }
  paint(lastCount);
  load().catch(() => {});
  if (!window.EventSource) return;
  const source = new EventSource("/notifications/events");
  source.addEventListener("change", () => load().catch(() => {}));
  // Check again whenever the stream (re)connects: anything that arrived between loading the page and
  // connecting, or while the site restarted, would otherwise be missed.
  source.addEventListener("open", () => load().catch(() => {}));
})();
