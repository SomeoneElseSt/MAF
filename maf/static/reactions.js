// Emoji reactions on posts and comments, on the thread page only.
// Each .reactions box carries its counts in data-reactions and your own picks in
// data-mine. Every chip is already a small form (POST /react); this adds the picker (the smiley
// opens a grid of the fixed set) and sends reactions without reloading the page.
// Without JS the chips and the <details> picker work as plain forms.
(function () {
  const picker = document.querySelector(".emoji-picker");
  if (!picker) return;
  let pickerFor = null;

  // Reacting updates the chips in place, without a reload or a new history entry, so Back still
  // goes to the page you came from. If anything is off (signed out, slowed down), it falls back to
  // loading the result page in place of this one.
  // live.js waits for this before looking for new reactions, so your own never count as new.
  function submit(box, emoji) {
    window.mafReactionSent = send(box, emoji);
    return window.mafReactionSent;
  }

  async function send(box, emoji) {
    const body = new FormData();
    body.set("item_id", box.dataset.item);
    body.set("emoji", emoji);
    body.set("thread_id", document.querySelector("[data-thread]")?.dataset.thread ?? "");
    try {
      const response = await fetch("/react", { method: "POST", body });
      const url = new URL(response.url);
      const fresh = response.ok && !url.searchParams.has("notice") && url.pathname === window.location.pathname
        ? new DOMParser().parseFromString(await response.text(), "text/html")
            .querySelector(`.reactions[data-item="${CSS.escape(box.dataset.item)}"]`)
        : null;
      if (!fresh) {
        window.location.replace(response.url);
        return;
      }
      box.replaceWith(document.adoptNode(fresh));
    } catch {
      window.location.replace(window.location.href);
    }
  }

  function closePicker() {
    if (picker.hidden) return;
    picker.hidden = true;
    document.querySelector("main").style.paddingBottom = "";
    pickerFor?.querySelector(".react-add")?.setAttribute("aria-expanded", "false");
    pickerFor?.querySelector(".react-add")?.focus({ preventScroll: true });
    pickerFor = null;
  }

  function openPicker(box, button) {
    const reopening = pickerFor === box && !picker.hidden;
    closePicker();
    if (reopening) return;
    pickerFor = box;
    const mine = new Set((box.dataset.mine || "").split(" ").filter(Boolean));
    picker.replaceChildren(...picker.dataset.emoji.split(" ").map(emoji => {
      const option = document.createElement("button");
      option.type = "button";
      option.textContent = emoji;
      option.setAttribute("aria-pressed", String(mine.has(emoji)));
      option.addEventListener("click", () => { closePicker(); submit(box, emoji); });
      return option;
    }));
    picker.hidden = false;
    button.setAttribute("aria-expanded", "true");
    const anchor = button.getBoundingClientRect();
    const column = document.querySelector(".page").getBoundingClientRect();
    const left = Math.min(anchor.left, column.right - 20 - picker.offsetWidth);
    picker.style.left = `${Math.max(column.left + 20, left) + window.scrollX}px`;
    picker.style.top = `${anchor.bottom + window.scrollY + 6}px`;
    picker.querySelector("button")?.focus({ preventScroll: true });
    makeRoom();
  }

  // The picker is positioned in the page flow, so near the bottom it would hang over the footer.
  // Give main that much extra room at the end instead, and take it back when the picker closes.
  function makeRoom() {
    const main = document.querySelector("main");
    const footer = document.querySelector(".foot");
    // The footer sits right under main, so measured now its top is where main ends: how far the
    // picker reaches past it is how much room main needs for the footer to move down.
    const overlap = footer ? picker.getBoundingClientRect().bottom - footer.getBoundingClientRect().top : 0;
    const room = Math.max(0, Math.ceil(overlap) + 12);
    main.style.paddingBottom = room ? `${room}px` : "";
  }

  // Delegated, so chips that were just swapped in keep working.
  document.addEventListener("submit", event => {
    const form = event.target.closest(".react-form");
    if (!form) return;
    event.preventDefault();
    submit(form.closest(".reactions"), form.querySelector("input[name=emoji]").value);
  });
  document.addEventListener("click", event => {
    const add = event.target.closest(".react-add");
    if (add) {
      event.stopPropagation();
      openPicker(add.closest(".reactions"), add);
      return;
    }
    if (!event.target.closest(".emoji-picker")) closePicker();
  });
  document.addEventListener("keydown", event => {
    if (event.key === "Escape") closePicker();
    // The grid is rows of emoji: moving down from its last row would scroll to the footer instead.
    else if (!picker.hidden && event.key === "ArrowDown") {
      const buttons = [...picker.querySelectorAll("button")];
      const index = buttons.indexOf(event.target);
      if (index >= 0 && index + 8 >= buttons.length) event.preventDefault();
    }
  });
})();
