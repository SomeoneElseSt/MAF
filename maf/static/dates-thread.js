// A Dates thread. Reply with profile: without a profile it opens the notice under it. (Sending your profile
// as a private reply comes with profiles themselves.) Match, on your own profile: asks first, then opens a
// private reply to that person, which stays open until it's sent, and Match and Hide become Unmatch.
// Hide and Unmatch ask first. (Doing them comes with profiles' backend.)
(function () {
  const replyButton = document.getElementById("reply-with-profile");
  const notice = document.getElementById("need-profile");
  if (replyButton && notice) {
    replyButton.addEventListener("click", () => {
      notice.hidden = !notice.hidden;
      replyButton.setAttribute("aria-expanded", String(!notice.hidden));
    });
  }

  const dialogs = {
    match: document.getElementById("match-dialog"),
    hide: document.getElementById("hide-dialog"),
    unmatch: document.getElementById("unmatch-dialog"),
  };
  if (!dialogs.match) return;
  let matching = null; // the Match button whose dialog is open

  // One listener, so buttons added later (Unmatch, after matching) work too.
  document.addEventListener("click", event => {
    const button = event.target.closest("button.match, button.hide-profile, button.unmatch");
    if (!button) return;
    if (button.matches(".match")) matching = button;
    const which = button.matches(".match") ? "match" : button.matches(".unmatch") ? "unmatch" : "hide";
    dialogs[which].showModal();
  });
  for (const [name, box] of Object.entries(dialogs)) {
    box.querySelector(`[data-${name}-no]`).addEventListener("click", () => box.close());
    if (name !== "match") box.querySelector(`[data-${name}-yes]`).addEventListener("click", () => box.close());
  }

  dialogs.match.querySelector("[data-match-yes]").addEventListener("click", () => {
    dialogs.match.close();
    if (!matching) return;
    const form = document.getElementById(matching.dataset.reply);
    const actions = matching.closest(".actions");
    actions.querySelector("button.hide-profile")?.remove();
    const unmatch = document.createElement("button");
    unmatch.type = "button";
    unmatch.className = "unmatch";
    unmatch.textContent = "Unmatch";
    matching.replaceWith(unmatch);
    matching = null;
    if (!form) return;
    form.hidden = false;
    form.querySelector(".cancel")?.remove(); // the first message opens the conversation, so the box stays
    form.querySelector("textarea")?.focus();
  });
})();
