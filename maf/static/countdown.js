// Sign-in cooldown.
// Code page: "Send a new code" always shows that label. Clicked before the cooldown is over, it says
// "Wait N seconds", counts down, then goes back to "Send a new code". Sign in page: the banner counts down.
(function () {
  const TICK_MS = 1000;
  const resend = document.querySelector(".resend[data-seconds]");
  const bannerCounter = document.querySelector(".notice .countdown[data-seconds]");
  const startedAt = Date.now();

  const secondsLeft = initial => Math.max(0, initial - Math.floor((Date.now() - startedAt) / TICK_MS));

  function setUpResend(button) {
    const initial = Number(button.dataset.seconds) || 0;
    let waiting = false;
    button.addEventListener("click", event => {
      if (secondsLeft(initial) === 0 || waiting) {
        if (waiting) event.preventDefault();
        return;
      }
      event.preventDefault();
      waiting = true;
      button.disabled = true;
      const update = () => {
        const left = secondsLeft(initial);
        if (left > 0) {
          button.textContent = `Wait ${left} second${left === 1 ? "" : "s"}`;
          return;
        }
        clearInterval(timer);
        waiting = false;
        button.disabled = false;
        button.textContent = "Send a new code";
      };
      const timer = setInterval(update, TICK_MS);
      update();
    });
  }

  function setUpBanner(counter) {
    const initial = Number(counter.dataset.seconds) || 0;
    const timer = setInterval(() => {
      const left = secondsLeft(initial);
      if (left > 0) {
        counter.textContent = String(left);
        return;
      }
      clearInterval(timer);
      counter.closest("p").textContent = "A code was already sent to this address. You can send a new one now.";
    }, TICK_MS);
  }

  if (resend) setUpResend(resend);
  if (bannerCounter) setUpBanner(bannerCounter);
})();
