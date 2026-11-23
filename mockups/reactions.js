// Mockup-only: emoji reactions on posts and comments. Each .reactions element carries its counts in
// data-reactions and your own picks in data-mine. Clicking a reaction toggles yours; the smiley opens a picker.
const PICKER_EMOJI = ["👍", "❤️", "😂", "😮", "😢", "🔥", "🎉", "🤔", "👀", "🙏", "💯", "🙌", "😅", "🫠", "💀", "🤝", "👏", "🫶", "😬", "🙃", "✅", "📌", "☕", "🌱"];
const ADD_ICON = `<svg viewBox="0 0 18 16" width="18" height="16" aria-hidden="true"><circle cx="7.5" cy="8.5" r="6" fill="none" stroke="currentColor" stroke-width="1.2"/><circle cx="5.5" cy="7.3" r=".8" fill="currentColor"/><circle cx="9.5" cy="7.3" r=".8" fill="currentColor"/><path d="M5 10.3c1.4 1.5 3.6 1.5 5 0" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/><path d="M15 1v4M13 3h4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>`;

const picker = document.createElement("div");
picker.className = "emoji-picker";
picker.setAttribute("role", "dialog");
picker.setAttribute("aria-label", "Add a reaction");
picker.hidden = true;
document.body.append(picker);
let pickerFor = null;

const stateOf = box => ({
  counts: JSON.parse(box.dataset.reactions || "{}"),
  mine: new Set((box.dataset.mine || "").split(" ").filter(Boolean)),
});

function saveState(box, { counts, mine }) {
  box.dataset.reactions = JSON.stringify(counts);
  box.dataset.mine = [...mine].join(" ");
}

function toggleReaction(box, emoji) {
  const state = stateOf(box);
  const had = state.mine.has(emoji);
  state.counts[emoji] = (state.counts[emoji] ?? 0) + (had ? -1 : 1);
  had ? state.mine.delete(emoji) : state.mine.add(emoji);
  if (state.counts[emoji] === 0) delete state.counts[emoji];
  saveState(box, state);
  render(box);
}

function render(box) {
  const { counts, mine } = stateOf(box);
  const chips = Object.entries(counts).map(([emoji, count]) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "react";
    chip.setAttribute("aria-pressed", String(mine.has(emoji)));
    chip.setAttribute("aria-label", `${emoji} ${count}${mine.has(emoji) ? ", including you" : ""}. ${mine.has(emoji) ? "Remove" : "Add"} your reaction`);
    chip.innerHTML = `<span class="react-emoji">${emoji}</span><span class="react-count">${count}</span>`;
    chip.addEventListener("click", () => toggleReaction(box, emoji));
    return chip;
  });
  const add = document.createElement("button");
  add.type = "button";
  add.className = "react-add";
  add.setAttribute("aria-label", "Add a reaction");
  add.setAttribute("aria-expanded", "false");
  add.innerHTML = ADD_ICON;
  add.addEventListener("click", event => { event.stopPropagation(); openPicker(box, add); });
  box.replaceChildren(...chips, add);
}

function openPicker(box, button) {
  const reopening = pickerFor === box && !picker.hidden;
  closePicker();
  if (reopening) return;
  pickerFor = box;
  const { mine } = stateOf(box);
  picker.replaceChildren(...PICKER_EMOJI.map(emoji => {
    const option = document.createElement("button");
    option.type = "button";
    option.textContent = emoji;
    option.setAttribute("aria-pressed", String(mine.has(emoji)));
    option.addEventListener("click", () => { closePicker(); toggleReaction(box, emoji); });
    return option;
  }));
  picker.hidden = false;
  button.setAttribute("aria-expanded", "true");
  // Below the button, kept inside the content column.
  const anchor = button.getBoundingClientRect();
  const column = document.querySelector(".page").getBoundingClientRect();
  const left = Math.min(anchor.left, column.right - 20 - picker.offsetWidth);
  picker.style.left = `${Math.max(column.left + 20, left) + window.scrollX}px`;
  picker.style.top = `${anchor.bottom + window.scrollY + 6}px`;
  picker.querySelector("button").focus();
}

function closePicker() {
  if (picker.hidden) return;
  picker.hidden = true;
  pickerFor?.querySelector(".react-add")?.setAttribute("aria-expanded", "false");
  pickerFor?.querySelector(".react-add")?.focus({ preventScroll: true });
  pickerFor = null;
}

document.addEventListener("click", event => { if (!event.target.closest(".emoji-picker")) closePicker(); });
document.addEventListener("keydown", event => { if (event.key === "Escape") closePicker(); });
document.querySelectorAll(".reactions").forEach(render);
