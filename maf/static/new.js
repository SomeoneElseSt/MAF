// New: the front page's section of posts you haven't caught up on, until you open them. A post is in New when
// someone else posted it, or commented on it, after you last opened it (and after this browser started
// counting). Opening a post is what takes it out: reloading or scrolling past doesn't. What you've opened
// stays in this browser; the server only hears when this browser started counting.
(function () {
  const SINCE_KEY = "maf.new-since"; // when this browser started counting
  const OPENED_KEY = "maf.opened"; // {post id: when you last opened it}
  const OLD_LAST_VISIT_KEY = "maf.comments-seen"; // the earlier "New comments" labels' last visit
  const OLD_SEEN_KEY = "maf.seen";

  function read(key) {
    try {
      return localStorage.getItem(key);
    } catch {
      return null;
    }
  }

  function write(key, value) {
    try {
      localStorage.setItem(key, value);
    } catch {
      // Storage off: New stays empty, everything else works.
    }
  }

  function opened() {
    try {
      return JSON.parse(read(OPENED_KEY) || "{}");
    } catch {
      return {};
    }
  }

  // A post: you've opened it now. The server's time, so a wrong clock on this device can't hide comments.
  const post = document.querySelector("article.post-head[data-now]");
  if (post) {
    write(OPENED_KEY, JSON.stringify({ ...opened(), [post.id]: post.dataset.now }));
    return;
  }

  const newList = document.querySelector(".new-list");
  if (!newList) return;

  // Times are UTC ISO strings, so comparing them as text compares them as times.
  // The first visit starts counting: New starts empty. Coming from the old labels, count from your last visit.
  let since = read(SINCE_KEY);
  if (!since) {
    since = read(OLD_LAST_VISIT_KEY)?.replace(/\.\d+Z$/, "Z") || newList.dataset.now;
    write(SINCE_KEY, since);
  }
  try {
    localStorage.removeItem(OLD_LAST_VISIT_KEY);
    localStorage.removeItem(OLD_SEEN_KEY);
  } catch {
    // Nothing to clean up.
  }
  const openedAt = opened();
  const heading = document.getElementById("new-heading");

  // What's new about a row, or null: "New" for a post you haven't opened, "New comments" otherwise.
  function whatsNew(row) {
    const last = openedAt[row.dataset.id] ?? "";
    const after = last > since ? last : since;
    if (!("mine" in row.dataset) && !last && row.dataset.created > since) return "New";
    if ((row.dataset.latestComment ?? "") > after) return "New comments";
    return null;
  }

  const lastActivity = row => {
    const comment = row.dataset.latestComment ?? "";
    return comment > row.dataset.created ? comment : row.dataset.created;
  };

  const homes = new Map(); // row -> [its day list, the row after it], to put it back once opened

  function addToNew(row, label) {
    if (row.parentElement) homes.set(row, [row.parentElement, row.nextElementSibling]);
    const tag = document.createElement("span");
    tag.className = "new-tag";
    tag.textContent = label;
    row.querySelector(".meta")?.append(tag);
    newList.append(row);
  }

  // Back from a post you opened from New, with the page as you left it: it goes back to its day.
  function dropOpened() {
    Object.assign(openedAt, opened());
    for (const row of [...newList.children]) {
      if (whatsNew(row)) continue;
      row.querySelector(".new-tag")?.remove();
      const [list, next] = homes.get(row) ?? [];
      if (!list) row.remove();
      else if (next?.parentElement === list) list.insertBefore(row, next);
      else list.append(row);
    }
    settle();
  }

  // Newest activity first, then show the section and hide days left empty.
  function settle() {
    [...newList.children].sort((a, b) => (lastActivity(a) < lastActivity(b) ? 1 : -1)).forEach(row => newList.append(row));
    const empty = newList.children.length === 0;
    newList.hidden = empty;
    heading.hidden = empty;
    document.querySelectorAll("ol.list:not(.pinned-list):not(.new-list)").forEach(list => {
      const left = list.children.length === 0;
      list.hidden = left;
      if (list.previousElementSibling?.matches("h2.day")) list.previousElementSibling.hidden = left;
    });
  }

  // Posts on this page move up into New straight away (only in New, not also in their day).
  const pinnedIds = new Set([...document.querySelectorAll(".pinned-list li[data-id]")].map(row => row.dataset.id));
  const dayRows = [...document.querySelectorAll("ol.list:not(.pinned-list):not(.new-list) > li[data-id][data-created]")];
  for (const row of dayRows) {
    const label = whatsNew(row);
    if (label) addToNew(row, label);
  }
  settle();

  // Older posts with new comments aren't on this page: the server sends their rows.
  async function addOlder() {
    const response = await fetch(`/new-activity?since=${encodeURIComponent(since)}`, { headers: { accept: "text/html" } });
    if (!response.ok) return;
    const page = new DOMParser().parseFromString(await response.text(), "text/html");
    const shown = new Set([...document.querySelectorAll("li[data-id]")].map(row => row.dataset.id));
    for (const row of page.querySelectorAll("li[data-id][data-created]")) {
      if (shown.has(row.dataset.id) || pinnedIds.has(row.dataset.id)) continue;
      const label = whatsNew(row);
      if (label) addToNew(document.adoptNode(row), label);
    }
    settle();
  }
  addOlder().catch(() => {});
  window.addEventListener("pageshow", event => {
    if (event.persisted) dropOpened();
  });
})();
