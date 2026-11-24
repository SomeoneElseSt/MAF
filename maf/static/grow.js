// Text boxes grow as you type (and when a draft is restored), so you never scroll inside one.
// They never shrink below their CSS min-height.
(function () {
  function fit(box) {
    if (!box.offsetParent) return; // hidden reply boxes are fitted when they're opened and focused
    box.style.height = "auto";
    box.style.height = `${box.scrollHeight + box.offsetHeight - box.clientHeight}px`;
  }
  const isBox = target => target instanceof HTMLTextAreaElement;
  document.addEventListener("input", event => { if (isBox(event.target)) fit(event.target); });
  document.addEventListener("focusin", event => { if (isBox(event.target)) fit(event.target); });
  document.querySelectorAll("textarea").forEach(fit);
})();
