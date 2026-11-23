// Sign-in cooldown, counted down once a second.
// On the code page it's the "Send a new code" button, which unlocks at zero; on Sign in it's the error line.
(function () {
  const resend = document.querySelector(".resend[data-seconds]");
  const counter = document.querySelector(".countdown");
  if (!counter) return;
  let left = Number((resend ?? counter).dataset.seconds ?? counter.dataset.seconds);

  function finish() {
    if (resend) {
      resend.disabled = false;
      resend.textContent = "Send a new code";
      return;
    }
    counter.closest("p").textContent = "A code was already sent to that address. You can send a new one now.";
  }

  const timer = setInterval(() => {
    left -= 1;
    if (left > 0) {
      counter.textContent = String(left);
      return;
    }
    clearInterval(timer);
    finish();
  }, 1000);
})();
