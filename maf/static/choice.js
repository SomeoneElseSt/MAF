// Pick-one questions (the Dates profile form): each box opens a dropdown, the same panel as Is NSFW?.
// The box is read-only: an answer only comes from the dropdown, or the keyboard (arrows, Enter, a first letter).
// Long lists scroll with the hashtag menu's fades and chevrons (scrollArrow and updateTagFade, from tags.js).
(function () {
  function setUp(field) {
    const box = field.querySelector(".choice-answer");
    const menu = field.querySelector(".tag-menu");
    const scroller = menu.querySelector(".tag-scroll");
    const choices = [...menu.querySelectorAll("button[data-answer]")];
    menu.prepend(scrollArrow("up", scroller));
    menu.append(scrollArrow("down", scroller));
    scroller.addEventListener("scroll", () => updateTagFade(menu));

    function show(open) {
      menu.hidden = !open;
      box.setAttribute("aria-expanded", String(open));
      if (open) updateTagFade(menu);
    }

    function answer(value) {
      box.value = value;
      show(false);
      box.focus();
    }

    function startingWith(letter) {
      return choices.find(choice => choice.dataset.answer.toLowerCase().startsWith(letter));
    }

    box.addEventListener("click", () => show(menu.hidden));
    box.addEventListener("keydown", event => {
      if (event.key === "Enter" || event.key === " " || event.key === "ArrowDown") {
        event.preventDefault();
        show(true);
        (choices.find(choice => choice.dataset.answer === box.value) || choices[0]).focus();
        return;
      }
      if (event.key === "Escape") { show(false); return; }
      const match = event.key.length === 1 && startingWith(event.key.toLowerCase());
      if (match) box.value = match.dataset.answer;
    });
    menu.addEventListener("keydown", event => {
      const at = choices.indexOf(document.activeElement);
      if (event.key === "ArrowDown") { event.preventDefault(); choices[Math.min(at + 1, choices.length - 1)].focus(); }
      if (event.key === "ArrowUp") { event.preventDefault(); choices[Math.max(at - 1, 0)].focus(); }
      if (event.key === "Escape") { show(false); box.focus(); }
    });
    choices.forEach(choice => choice.addEventListener("click", () => answer(choice.dataset.answer)));
    document.addEventListener("click", event => {
      if (!field.contains(event.target)) show(false);
    });
  }

  document.querySelectorAll(".choice-field").forEach(setUp);
})();
