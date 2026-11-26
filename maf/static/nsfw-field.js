// The "Is NSFW?" box opens a Yes / No dropdown, the same panel as the Hashtags suggestions.
// The box is read-only: an answer only comes from the dropdown (or the keyboard: Y, N, arrows, Enter).
(function () {
  const box = document.getElementById("nsfw");
  const menu = document.getElementById("nsfw-menu");
  if (!box || !menu) return;
  const choices = [...menu.querySelectorAll("button[data-answer]")];

  function show(open) {
    menu.hidden = !open;
    box.setAttribute("aria-expanded", String(open));
  }

  function answer(value) {
    box.value = value;
    show(false);
    box.dispatchEvent(new Event("input", { bubbles: true }));
  }

  box.addEventListener("click", () => show(menu.hidden));
  box.addEventListener("keydown", event => {
    const key = event.key.toLowerCase();
    if (key === "y") answer("Yes");
    else if (key === "n") answer("No");
    else if (key === "enter" || key === " " || key === "arrowdown") { event.preventDefault(); show(true); choices[0].focus(); }
    else if (key === "escape") show(false);
  });
  menu.addEventListener("keydown", event => {
    const at = choices.indexOf(document.activeElement);
    if (event.key === "ArrowDown") { event.preventDefault(); choices[Math.min(at + 1, choices.length - 1)].focus(); }
    if (event.key === "ArrowUp") { event.preventDefault(); choices[Math.max(at - 1, 0)].focus(); }
    if (event.key === "Escape") { show(false); box.focus(); }
  });
  choices.forEach(choice => choice.addEventListener("click", () => { answer(choice.dataset.answer); box.focus(); }));
  document.addEventListener("click", event => {
    if (!event.target.closest(".tag-field") || !menu.parentElement.contains(event.target)) show(false);
  });
})();
