// The name check's warning sits inside the box it belongs to. "Edit" takes it away and puts the
// cursor back in the words, and arriving on a refused box focuses it, so the person lands where they were.
(function () {
  const warning = document.querySelector(".name-warning");
  if (!warning) return;
  const form = warning.closest("form");

  warning.querySelector("[data-edit-warning]")?.addEventListener("click", () => {
    warning.remove();
    const box = form.querySelector("textarea");
    box.focus();
    box.selectionStart = box.selectionEnd = box.value.length;
  });

  const box = form.querySelector("textarea");
  if (box) box.focus({ preventScroll: true });
  form.scrollIntoView({ block: "nearest" });
})();
