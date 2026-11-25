// New: the front page's section of posts you haven't caught up on, until you open them. A post is in New when
// someone else posted it, or commented on it, after you last opened it (and after this browser started
// counting). Opening a post is what takes it out: reloading or scrolling past doesn't. What you've opened
// stays in this browser; the server only hears when this browser started counting.
(function () {
  const SINCE_KEY = "maf.new-since"; // when this browser started counting
  const OPENED_KEY = "maf.opened"; // {post id: when you last opened it}
  const BEFORE_KEY = "maf.opened-before"; // {post id: the visit before that}, for marking what's new in it
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

  function readMap(key) {
    try {
      return JSON.parse(read(key) || "{}");
    } catch {
      return {};
    }
  }
  const opened = () => readMap(OPENED_KEY);

  // A post: you've opened it now. The server's time, so a wrong clock on this device can't hide comments.
  const post = document.querySelector("article.post-head[data-now]");
  if (post) {
    markNewSinceLastVisit(post);
    return;
  }

  // What came in since your last visit to this post: a "New" label on replies by others, a highlight on emoji
  // others added, and the page opens at the earliest new reply. A reload or Back keeps the same marks
  // (the visit they compare with is kept until you open the post again).
  function markNewSinceLastVisit(post) {
    const navigation = performance.getEntriesByType("navigation")[0]?.type;
    const sameVisit = navigation === "reload" || navigation === "back_forward";
    const before = readMap(BEFORE_KEY);
    const openedAt = opened();
    const since = sameVisit ? before[post.id] ?? openedAt[post.id] : openedAt[post.id];
    if (!sameVisit) write(BEFORE_KEY, JSON.stringify({ ...before, [post.id]: openedAt[post.id] ?? "" }));
    write(OPENED_KEY, JSON.stringify({ ...openedAt, [post.id]: post.dataset.now }));
    if (!since) return; // first visit: everything is new, so nothing is marked

    const newReplies = [...document.querySelectorAll("li.comment[data-created]")].filter(
      reply => !("mine" in reply.dataset) && reply.dataset.created > since,
    );
    for (const reply of newReplies) {
      const tag = Object.assign(document.createElement("span"), { className: "new-tag", textContent: "New" });
      reply.querySelector(":scope > .meta")?.append(tag);
    }
    document.querySelectorAll("button.react[data-latest]").forEach(chip => {
      if (chip.dataset.latest > since) chip.classList.add("react-new");
    });

    // Opening the post (not a reload, Back, or a link to a particular reply): start at the earliest new reply.
    if (sameVisit || location.hash || !newReplies.length) return;
    const earliest = newReplies.reduce((first, reply) => (reply.dataset.created < first.dataset.created ? reply : first));
    requestAnimationFrame(() => earliest.scrollIntoView({ block: "start" }));
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

  // The server's latest: older posts with new comments (not on this page) come in as rows, and posts on
  // the page take its newest comment times, so a reply that arrived since this page was made still counts
  // (coming back with Back shows the page as it was).
  async function refreshNew() {
    // no-store: while a page brought back by Back loads, the browser may answer from its old saved copies.
    const response = await fetch(`/new-activity?since=${encodeURIComponent(since)}`, { cache: "no-store", headers: { accept: "text/html" } });
    if (!response.ok) return;
    const page = new DOMParser().parseFromString(await response.text(), "text/html");
    for (const row of page.querySelectorAll("li[data-id][data-created]")) {
      if (pinnedIds.has(row.dataset.id)) continue;
      const shown = document.querySelector(`ol.list:not(.pinned-list) > li[data-id="${CSS.escape(row.dataset.id)}"]`);
      if (shown && row.dataset.latestComment) shown.dataset.latestComment = row.dataset.latestComment;
      const target = shown ?? row;
      const label = whatsNew(target);
      if (!label || target.parentElement === newList) continue;
      addToNew(shown ?? document.adoptNode(row), label);
    }
    settle();
  }
  refreshNew().catch(() => {});
  // Live: when someone posts or comments, and when you come back to this tab (anything missed meanwhile).
  window.addEventListener("maf:activity", () => refreshNew().catch(() => {}));
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") refreshNew().catch(() => {});
  });
  window.addEventListener("pageshow", event => {
    if (!event.persisted) return;
    dropOpened();
    refreshNew().catch(() => {});
  });
})();
