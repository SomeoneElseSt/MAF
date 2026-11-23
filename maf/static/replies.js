// Reply boxes under comments are <details> elements, so they open without JS.
// This keeps only one open at a time and focuses its textarea.
(function () {
  document.querySelectorAll(".reply-details").forEach(details => {
    details.addEventListener("toggle", () => {
      if (!details.open) return;
      document.querySelectorAll(".reply-details[open]").forEach(other => {
        if (other !== details) other.open = false;
      });
      details.querySelector("textarea")?.focus();
    });
  });

  // The per-thread ID in a reply box opens the same pop-up as IDs elsewhere.
  document.querySelectorAll(".inline-reply .id").forEach(button => {
    button.addEventListener("click", () => document.getElementById("id-dialog")?.showModal());
  });
})();
