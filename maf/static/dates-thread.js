// A Dates thread. Reply with profile: without a profile it opens the notice under it. (Sending your profile
// as a private reply comes with profiles themselves.) Match, on your own profile: asks first, then opens a
// private reply to that person.
(function () {
  const replyButton = document.getElementById("reply-with-profile");
  const notice = document.getElementById("need-profile");
  if (replyButton && notice) {
    replyButton.addEventListener("click", () => {
      notice.hidden = !notice.hidden;
      replyButton.setAttribute("aria-expanded", String(!notice.hidden));
    });
  }

  const dialog = document.getElementById("match-dialog");
  if (!dialog) return;
  let form = null;
  document.querySelectorAll("button.match").forEach(button => button.addEventListener("click", () => {
    form = document.getElementById(button.dataset.reply);
    dialog.showModal();
  }));
  dialog.querySelector("[data-match-no]").addEventListener("click", () => dialog.close());
  dialog.querySelector("[data-match-yes]").addEventListener("click", () => {
    dialog.close();
    if (!form) return;
    form.hidden = false;
    const privately = form.querySelector('input[name="private"]');
    if (privately) privately.checked = true;
    form.querySelector("textarea")?.focus();
  });
})();
