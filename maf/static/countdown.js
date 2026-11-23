// Sign-in cooldown, shown on the button itself: "Wait N seconds", frozen, then back to its label.
// Sign in: a Send code button rendered with data-wait starts counting straight away.
// Code page: "Send a new code" only starts counting if it's clicked before the cooldown is over.
(function () {
  const TICK_MS = 1000;
  const startedAt = Date.now();
  const secondsLeft = initial => Math.max(0, initial - Math.floor((Date.now() - startedAt) / TICK_MS));

  // Freezes the button and counts down; at zero it gets its label back and works again.
  // Returns a function that stops the wait early.
  function wait(button, initial, label) {
    const release = () => {
      clearInterval(timer);
      button.disabled = false;
      button.textContent = label;
    };
    const update = () => {
      const left = secondsLeft(initial);
      if (left === 0) return release();
      button.textContent = `Wait ${left} second${left === 1 ? "" : "s"}`;
    };
    button.disabled = true;
    const timer = setInterval(update, TICK_MS);
    update();
    return release;
  }

  // The wait belongs to the address that hit the cooldown: editing the email lifts it, changing it back resumes it.
  const sendCode = document.querySelector("button[data-wait]");
  if (sendCode) {
    const initial = Number(sendCode.dataset.wait) || 0;
    const emailField = document.getElementById("email");
    const waitedFor = emailField.value.trim().toLowerCase();
    let stop = wait(sendCode, initial, "Send code");
    emailField.addEventListener("input", () => {
      stop();
      if (emailField.value.trim().toLowerCase() === waitedFor && secondsLeft(initial) > 0) {
        stop = wait(sendCode, initial, "Send code");
      }
    });
  }

  const resend = document.querySelector(".resend[data-seconds]");
  if (!resend) return;
  const initial = Number(resend.dataset.seconds) || 0;
  resend.addEventListener("click", event => {
    if (secondsLeft(initial) === 0) return;
    event.preventDefault();
    wait(resend, initial, "Send a new code");
  });
})();
