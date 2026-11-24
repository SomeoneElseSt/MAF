// A button with data-pending shows that label and greys out once its form is sent, so a slow
// server step (the name check) doesn't look like a hang. Coming back with Back resets it.
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
    window.addEventListener("pageshow", () => {
      button.textContent = label;
      button.disabled = false;
      form.removeAttribute("aria-busy");
    });
  });
})();
