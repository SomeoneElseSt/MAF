// Folding comments: [–] after a comment's time folds it and its replies down to its details line; [+] opens it.
// Folds are remembered in this browser, per post. Folding a comment yourself counts as reading it and what's under
// it, so their New badges go and stay gone; replying to a comment does the same for it. A branch folded on an earlier
// visit shows one badge with how much is new inside it (and the comment itself, if it's new). Without JS, nothing folds.
(function () {
  const post = document.querySelector("article.post-head");
  if (!post) return;
  const FOLDED_KEY = `maf.folded.${post.id}`;
  const READ_KEY = `maf.read-by-folding.${post.id}`;

  function readSet(key) {
    try {
      return new Set(JSON.parse(localStorage.getItem(key) || "[]"));
    } catch {
      return new Set();
    }
  }

  function writeSet(key, set) {
    try {
      localStorage.setItem(key, JSON.stringify([...set]));
    } catch {
      // Storage off: folding still works until the page reloads.
    }
  }

  const folded = readSet(FOLDED_KEY);
  const read = readSet(READ_KEY);
  const words = n => `${n} ${n === 1 ? "reply" : "replies"}`;
  const ownBadge = li => li.querySelector(":scope > .meta > .new-tag:not(.fold-new)");
  const newInside = li => [...li.querySelectorAll(":scope > ol.comments li.comment")].filter(ownBadge).length;

  // Read by folding on an earlier visit: no New badge (new.js and live.js put them on before this runs).
  for (const id of read) {
    const li = document.getElementById(id);
    if (li) ownBadge(li)?.remove();
  }

  function markRead(li) {
    for (const each of [li, ...li.querySelectorAll("li.comment")]) {
      const badge = ownBadge(each);
      if (!badge) continue;
      badge.remove();
      read.add(each.id);
    }
    writeSet(READ_KEY, read);
  }

  // Folded: one badge counting the comment (if new) and everything new under it; open: the comment's own badge.
  function showFolded(li, isFolded) {
    const meta = li.querySelector(":scope > .meta");
    const button = meta.querySelector(":scope > .fold");
    li.classList.toggle("folded", isFolded);
    button.textContent = isFolded ? "[+]" : "[–]";
    button.setAttribute("aria-expanded", String(!isFolded));
    meta.querySelector(":scope > .fold-new")?.remove();
    const own = ownBadge(li);
    if (own) own.style.display = isFolded ? "none" : "";
    const total = newInside(li) + (own ? 1 : 0);
    if (!isFolded || !total) return;
    const badge = Object.assign(document.createElement("span"), { className: "new-tag fold-new" });
    badge.textContent = total === 1 && own ? "New" : `${total} New`;
    meta.querySelector(":scope > .fold-count").after(badge);
  }

  function addFold(li) {
    const meta = li.querySelector(":scope > .meta");
    if (!meta) return;
    const n = li.querySelectorAll(":scope > ol.comments li.comment").length;
    const dot = Object.assign(document.createElement("span"), { className: "dot", textContent: "·" });
    const button = Object.assign(document.createElement("button"), { type: "button", className: "fold" });
    button.setAttribute("aria-label", "Fold this comment");
    const count = Object.assign(document.createElement("span"), { className: "fold-count" });
    count.textContent = n ? ` (${words(n)} hidden)` : " (hidden)";
    const time = meta.querySelector(":scope > .edited") || meta.querySelector(":scope > time"); // after "(edited)"
    // Spaced like the details line's other dots (" · Private, only you and …").
    if (time) time.after(" ", dot, " ", button, count);
    else meta.append(" ", dot, " ", button, count);
    button.addEventListener("click", () => {
      const folding = !li.classList.contains("folded");
      if (folding) markRead(li);
      if (folding) folded.add(li.id);
      else folded.delete(li.id);
      writeSet(FOLDED_KEY, folded);
      showFolded(li, folding);
    });
    showFolded(li, folded.has(li.id));
  }

  // Profiles on Dates are private conversations between two people: nothing to fold there.
  document.querySelectorAll("li.comment").forEach(li => {
    if (li.closest(".profile-replies")) return;
    addFold(li);
  });

  // Replying to a comment counts as reading it: its New badge goes, and stays gone after the reload that follows.
  document.addEventListener("submit", event => {
    const form = event.target.closest?.("form.inline-reply[id^='reply-']");
    const li = form?.closest("li.comment");
    if (!li) return;
    ownBadge(li)?.remove();
    read.add(li.id);
    writeSet(READ_KEY, read);
  }, true);

  // A link to a reply inside a folded branch (from the Feed, or after sending one) opens the branch to it.
  function openTo(id) {
    const target = id && document.getElementById(id);
    if (!target?.matches?.("li.comment")) return;
    for (let li = target.parentElement.closest("li.comment.folded"); li; li = li.parentElement.closest("li.comment.folded")) {
      folded.delete(li.id);
      showFolded(li, false);
    }
    writeSet(FOLDED_KEY, folded);
    target.scrollIntoView({ block: "start" });
  }
  if (location.hash) openTo(decodeURIComponent(location.hash.slice(1)));
  window.addEventListener("hashchange", () => openTo(decodeURIComponent(location.hash.slice(1))));

  // Where the page should start for a reply that's folded away: its outermost folded comment (used by new.js).
  window.mafVisibleComment = reply => {
    let shown = reply;
    for (let li = reply.parentElement.closest("li.comment.folded"); li; li = li.parentElement.closest("li.comment.folded")) shown = li;
    return shown;
  };
})();
