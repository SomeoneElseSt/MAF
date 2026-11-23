// Emoji reactions on posts and comments, on the thread page only.
// Each .reactions box carries its counts in data-reactions and your own picks in
// data-mine. Every chip is already a small form (POST /react), so this only adds
// the picker: the smiley opens a grid of the fixed set and submits that item's form.
// Without JS the chips and the <details> picker work as plain forms.
(function () {
  const picker = document.querySelector(".emoji-picker");
  if (!picker) return;
  let pickerFor = null;

  const formsFor = box => [...document.querySelectorAll(".react-form")].filter(form => form.closest(".reactions") === box);

  function submit(box, emoji) {
    const form = formsFor(box).find(f => f.querySelector("input[name=emoji]").value === emoji);
    if (form) { form.requestSubmit(); return; }
    const hidden = document.createElement("form");
    hidden.method = "post";
    hidden.action = "/react";
    hidden.innerHTML = `<input name="item_id" value="${box.dataset.item}"><input name="emoji" value="${emoji}">`;
    document.body.append(hidden);
    hidden.submit();
  }

  function closePicker() {
    if (picker.hidden) return;
    picker.hidden = true;
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
    picker.querySelector("button")?.focus();
  }

  document.querySelectorAll(".react-add").forEach(button => {
    button.addEventListener("click", event => { event.stopPropagation(); openPicker(button.closest(".reactions"), button); });
  });
  document.addEventListener("click", event => { if (!event.target.closest(".emoji-picker")) closePicker(); });
  document.addEventListener("keydown", event => { if (event.key === "Escape") closePicker(); });
})();
