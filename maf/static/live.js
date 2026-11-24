// Live updates on a thread page. The server only pings "something changed"; this page then fetches
// the thread as you and compares it with what it shows, so private replies (and reactions on them)
// between other people never surface. A banner says e.g. "1 new reply and 2 new reactions. Show?";
// Show reloads the page (drafts are kept), labels new replies "New", rings new reactions, and scrolls to them.
(function () {
  const root = document.querySelector("[data-thread]");
  const main = document.querySelector("main");
  if (!root || !main || !window.EventSource) return;

  let banner = null;
  let latest = { replies: [], reactions: [] };
  const ARRIVED_KEY = "maf.arrived";
  const RING_SECONDS = 2.5;

  // Show reloads, remembering what's new so the next page can mark it and scroll to it.
  function showNew() {
    try {
      sessionStorage.setItem(ARRIVED_KEY, JSON.stringify({ path: window.location.pathname, ...latest }));
      history.scrollRestoration = "manual";
    } catch {
      // Storage off: a plain reload still shows everything, just without the marks.
    }
    window.location.reload();
  }

  function reactionChip(item, emoji) {
    const box = document.querySelector(`.reactions[data-item="${CSS.escape(item)}"]`);
    if (!box) return null;
    return [...box.querySelectorAll("button.react")].find(chip => chip.querySelector(".react-emoji")?.textContent === emoji) || null;
  }

  // New replies get a "New" label (it stays until the next reload); reactions that went up get a ring
  // that fades. Then the page scrolls smoothly to the first of them.
  function markArrivals() {
    let arrived = null;
    try {
      arrived = JSON.parse(sessionStorage.getItem(ARRIVED_KEY));
      sessionStorage.removeItem(ARRIVED_KEY);
      history.scrollRestoration = "auto";
    } catch {
      return;
    }
    if (!arrived || arrived.path !== window.location.pathname) return;
    const marked = [];
    for (const id of arrived.replies) {
      const meta = document.getElementById(id)?.querySelector(":scope > .meta");
      if (!meta) continue;
      const tag = document.createElement("span");
      tag.className = "new-tag";
      tag.textContent = "New";
      meta.append(tag);
      marked.push(meta);
    }
    for (const { item, emoji } of arrived.reactions) {
      const chip = reactionChip(item, emoji);
      if (!chip) continue;
      chip.classList.add("arrived");
      setTimeout(() => chip.classList.add("arrived-fade"), 600);
      setTimeout(() => chip.classList.remove("arrived", "arrived-fade"), 600 + RING_SECONDS * 1000);
      marked.push(chip);
    }
    if (!marked.length) return;
    const first = marked.reduce((top, el) => (el.getBoundingClientRect().top < top.getBoundingClientRect().top ? el : top));
    const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    requestAnimationFrame(() => first.scrollIntoView({ block: "center", behavior: calm ? "auto" : "smooth" }));
  }
  markArrivals();

  function plural(count, one, many) {
    return `${count} new ${count === 1 ? one : many}`;
  }

  function showBanner(replies, reactions) {
    if (!banner) {
      banner = document.createElement("div");
      banner.className = "notice live-replies";
      banner.setAttribute("role", "status");
      banner.innerHTML = '<p><span class="live-count"></span> <button class="live-show" type="button">Show</button>?</p>';
      banner.querySelector(".live-show").addEventListener("click", showNew);
      main.prepend(banner);
    }
    const parts = [];
    if (replies) parts.push(plural(replies, "reply", "replies"));
    if (reactions) parts.push(plural(reactions, "reaction", "reactions"));
    banner.querySelector(".live-count").textContent = `${parts.join(" and ")}.`;
  }

  function reactionCounts(scope) {
    const counts = new Map();
    scope.querySelectorAll(".reactions[data-item]").forEach(box => {
      try {
        counts.set(box.dataset.item, JSON.parse(box.dataset.reactions || "{}"));
      } catch {
        counts.set(box.dataset.item, {});
      }
    });
    return counts;
  }

  // Reactions added since this page loaded, on posts and replies it already shows: [{item, emoji}].
  function newReactions(fresh) {
    const shown = reactionCounts(document);
    const added = [];
    for (const [item, counts] of reactionCounts(fresh)) {
      const before = shown.get(item);
      if (!before) continue;
      for (const [emoji, count] of Object.entries(counts)) {
        for (let n = before[emoji] || 0; n < count; n++) added.push({ item, emoji });
      }
    }
    return added;
  }

  function newReplies(fresh) {
    const shown = new Set([...document.querySelectorAll("li.comment[id]")].map(item => item.id));
    return [...fresh.querySelectorAll("li.comment[id]")].filter(item => !shown.has(item.id)).map(item => item.id);
  }

  async function check() {
    const response = await fetch(window.location.pathname, { headers: { accept: "text/html" } });
    if (!response.ok) return;
    const fresh = new DOMParser().parseFromString(await response.text(), "text/html");
    latest = { replies: newReplies(fresh), reactions: newReactions(fresh) };
    if (latest.replies.length || latest.reactions.length) showBanner(latest.replies.length, latest.reactions.length);
  }

  const source = new EventSource(`/thread/${root.dataset.thread}/events`);
  source.addEventListener("change", () => check().catch(() => {}));
  // After a reconnect (say, the site restarted), catch up on anything posted in between.
  let opened = false;
  source.addEventListener("open", () => {
    if (opened) check().catch(() => {});
    opened = true;
  });
})();
