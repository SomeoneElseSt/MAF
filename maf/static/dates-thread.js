// A Dates thread. Reply with profile: without a profile it opens the notice under it. (Sending your profile
// as a private reply comes with profiles themselves.) Match, on your own profile: asks first, then opens a
// private reply to that person, which stays open until it's sent, and Match and Hide become Unmatch. Until the
// first message, only this browser knows about the match (like the messages themselves), so it remembers it.
// Reply with profile, Hide and Unmatch ask first. (Doing them comes with profiles' backend.)
(function () {
  const replyButton = document.getElementById("reply-with-profile");
  const notice = document.getElementById("need-profile");
  if (replyButton && notice) {
    replyButton.addEventListener("click", () => {
      notice.hidden = !notice.hidden;
      replyButton.setAttribute("aria-expanded", String(!notice.hidden));
    });
  }

  // A button with data-opens="<dialog id>" opens that pop-up; data-closes inside it closes it.
  document.querySelectorAll("[data-opens]").forEach(button => button.addEventListener("click", () => document.getElementById(button.dataset.opens)?.showModal()));
  document.querySelectorAll("dialog [data-closes]").forEach(button => button.addEventListener("click", () => button.closest("dialog").close()));

  const dialogs = {
    match: document.getElementById("match-dialog"),
    hide: document.getElementById("hide-dialog"),
    send: document.getElementById("send-dialog"),
    unmatch: document.getElementById("unmatch-dialog"),
  };
  if (!dialogs.match) return;
  let matching = null; // the Match button whose dialog is open

  // One listener, so buttons added later (Unmatch, after matching) work too.
  document.addEventListener("click", event => {
    const button = event.target.closest("button.match, button.hide-profile, button.unmatch, button[data-send-profile]");
    if (!button) return;
    if (button.matches(".match")) matching = button;
    const which = button.matches(".match") ? "match" : button.matches(".unmatch") ? "unmatch" : button.matches("[data-send-profile]") ? "send" : "hide";
    dialogs[which].showModal();
  });
  for (const [name, box] of Object.entries(dialogs)) {
    box.querySelector(`[data-${name}-no]`).addEventListener("click", () => box.close());
    if (name !== "match") box.querySelector(`[data-${name}-yes]`).addEventListener("click", () => box.close());
  }

  // Matches made here that have no messages yet, by reply id. Once there are messages the page shows Unmatch itself.
  const KEY = "maf-dates-matched";
  const remembered = () => { try { return JSON.parse(localStorage.getItem(KEY) || "[]"); } catch { return []; } };
  const remember = ids => { try { localStorage.setItem(KEY, JSON.stringify(ids)); } catch {} };
  const replyIdOf = button => button.dataset.reply.replace(/^reply-/, "");

  function becomeMatched(button, focus) {
    const form = document.getElementById(button.dataset.reply);
    button.closest(".actions").querySelector("button.hide-profile")?.remove();
    const unmatch = document.createElement("button");
    unmatch.type = "button";
    unmatch.className = "unmatch";
    unmatch.dataset.unmatch = replyIdOf(button);
    unmatch.textContent = "Unmatch";
    button.replaceWith(unmatch);
    if (!form) return;
    form.hidden = false;
    form.querySelector(".cancel")?.remove(); // the first message opens the conversation, so the box stays
    if (focus) form.querySelector("textarea")?.focus();
  }

  dialogs.match.querySelector("[data-match-yes]").addEventListener("click", () => {
    dialogs.match.close();
    if (!matching) return;
    remember([...new Set([...remembered(), replyIdOf(matching)])]);
    becomeMatched(matching, true);
    matching = null;
  });

  // After a reload: matches still waiting for a first message open again; ones that have messages are forgotten.
  const waiting = new Set(remembered());
  const stillWaiting = [];
  document.querySelectorAll("button.match").forEach(button => {
    if (!waiting.has(replyIdOf(button))) return;
    stillWaiting.push(replyIdOf(button));
    becomeMatched(button, false);
  });
  const elsewhere = [...waiting].filter(id => !document.getElementById(id));  // other threads: keep
  remember([...elsewhere, ...stillWaiting]);
})();
