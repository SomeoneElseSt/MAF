// On "Check your inbox": asks the server once whether the code email actually went out. If the email
// service refused it, a banner offers to try again (the 30-second wait between codes is lifted for that).
(function () {
  const marker = document.querySelector("[data-send-check]");
  const codeForm = document.querySelector("form[action='/sign-in/code']");
  if (!marker || !codeForm || !document.getElementById("resend-form")) return;

  const body = new FormData();
  body.set("check", marker.dataset.sendCheck);
  fetch("/sign-in/sent", { method: "POST", body })
    .then(response => (response.ok ? response.json() : null))
    .then(result => {
      if (!result || result.sent !== false) return;
      const banner = document.createElement("div");
      banner.className = "notice";
      banner.setAttribute("role", "alert");
      banner.innerHTML = '<p>We couldn\'t send your code. <button class="live-show" type="submit" form="resend-form">Try again</button>?</p>';
      codeForm.before(banner);
    })
    .catch(() => {});
})();
