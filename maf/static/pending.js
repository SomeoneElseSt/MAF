// A button with data-pending shows that label and greys out once its form is sent, so a slow
// server step (the name check, sending an email) doesn't look like a hang. While it's busy the form's
// text boxes fade. Coming back with Back, or a script cancelling the send, resets it.
(function () {
  document.querySelectorAll("button[data-pending]").forEach(button => {
    const form = button.form;
    if (!form) return;
    const label = button.textContent;
    form.addEventListener("submit", event => {
      if (event.defaultPrevented) return;
      button.textContent = button.dataset.pending;
      button.disabled = true;
      form.setAttribute("aria-busy", "true");
    });
    const reset = () => {
      button.textContent = label;
      button.disabled = false;
      form.removeAttribute("aria-busy");
    };
    window.addEventListener("pageshow", reset);
    // Sent by other scripts when they stop a send themselves (e.g. a private reply that couldn't be encrypted).
    form.addEventListener("maf:not-sent", reset);
  });
})();
