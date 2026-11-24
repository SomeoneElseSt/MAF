// Live updates on a thread page. The server only pings "something changed"; this page then fetches
// the thread as you and compares it with what it shows, so private replies (and reactions on them)
// between other people never surface. A banner says e.g. "1 new reply and 2 new reactions. Show?";
// Show reloads the page (drafts are kept).
(function () {
  const root = document.querySelector("[data-thread]");
  const main = document.querySelector("main");
  if (!root || !main || !window.EventSource) return;

  let banner = null;

  function plural(count, one, many) {
    return `${count} new ${count === 1 ? one : many}`;
  }

  function showBanner(replies, reactions) {
    if (!banner) {
      banner = document.createElement("div");
      banner.className = "notice live-replies";
      banner.setAttribute("role", "status");
      banner.innerHTML = '<p><span class="live-count"></span> <button class="live-show" type="button">Show</button>?</p>';
      banner.querySelector(".live-show").addEventListener("click", () => window.location.reload());
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

  // Reactions added since this page loaded, on posts and replies it already shows.
  function newReactions(fresh) {
    const shown = reactionCounts(document);
    let added = 0;
    for (const [item, counts] of reactionCounts(fresh)) {
      const before = shown.get(item);
      if (!before) continue;
      for (const [emoji, count] of Object.entries(counts)) added += Math.max(0, count - (before[emoji] || 0));
    }
    return added;
  }

  function newReplies(fresh) {
    const shown = new Set([...document.querySelectorAll("li.comment[id]")].map(item => item.id));
    return [...fresh.querySelectorAll("li.comment[id]")].filter(item => !shown.has(item.id)).length;
  }

  async function check() {
    const response = await fetch(window.location.pathname, { headers: { accept: "text/html" } });
    if (!response.ok) return;
    const fresh = new DOMParser().parseFromString(await response.text(), "text/html");
    const replies = newReplies(fresh);
    const reactions = newReactions(fresh);
    if (replies || reactions) showBanner(replies, reactions);
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
