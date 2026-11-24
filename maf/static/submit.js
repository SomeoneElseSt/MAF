// The submit form's Text placeholder follows the hashtags: a house tag's outline,
// else the default outline, else the example post. Templates come from the server
// in the page's data attributes.
(function () {
  const form = document.querySelector("form[data-submit-form]");
  if (!form) return;
  const tagsInput = form.querySelector("#tags");
  const textBox = form.querySelector("#text");
  const templatesEl = document.getElementById("submit-templates");
  const templates = templatesEl ? JSON.parse(templatesEl.textContent) : null;
  const EXAMPLE = form.dataset.example ?? "";

  function apply() {
    const tags = tagsInput.value.toLowerCase().split(/[\s,]+/).map(t => t.replace(/^#/, "")).filter(Boolean);
    const house = tags.find(t => templates && templates[t]);
    if (house) { textBox.placeholder = templates[house].join("\n"); return; }
    if (tags.length) { textBox.placeholder = (templates?.default ?? []).join("\n"); return; }
    textBox.placeholder = EXAMPLE;
  }

  tagsInput.addEventListener("input", apply);
  apply();
})();

// Clicking into Hashtags drops down the suggested tags (house tags and #minerva); picking one adds it to the box.
// Typing narrows the list to tags that start with what's being typed. Hidden once 3 tags are in.
(function () {
  const input = document.querySelector("form[data-submit-form] #tags");
  const menu = document.getElementById("tag-suggest");
  if (!input || !menu) return;
  const PRESETS = (menu.dataset.tags ?? "").split(" ").filter(Boolean);
  const MAX_TAGS = 3;
  input.setAttribute("aria-controls", "tag-suggest");
  input.setAttribute("aria-expanded", "false");

  // The finished tags, and whatever is being typed after the last comma.
  function parts() {
    const pieces = input.value.split(",");
    const typing = pieces.pop().trim().replace(/^#/, "").toLowerCase();
    const done = pieces.map(t => t.trim().replace(/^#/, "").toLowerCase()).filter(Boolean);
    return { done, typing };
  }

  function close() {
    menu.hidden = true;
    input.setAttribute("aria-expanded", "false");
  }

  function pick(tag) {
    const { done } = parts();
    input.value = [...done, tag].map(t => `#${t}`).join(", ") + (done.length + 1 < MAX_TAGS ? ", " : "");
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.focus();
  }

  function open() {
    const { done, typing } = parts();
    const choices = PRESETS.filter(tag => !done.includes(tag) && tag.startsWith(typing) && tag !== typing);
    if (done.length >= MAX_TAGS || !choices.length) return close();
    menu.replaceChildren(...choices.map(tag => {
      const option = Object.assign(document.createElement("button"), { type: "button", textContent: `#${tag}` });
      option.addEventListener("mousedown", event => event.preventDefault()); // keep the cursor in the box
      option.addEventListener("click", () => pick(tag));
      return option;
    }));
    menu.hidden = false;
    input.setAttribute("aria-expanded", "true");
  }

  function moveFocus(event) {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    const options = [...menu.querySelectorAll("button")];
    if (menu.hidden || !options.length) return;
    event.preventDefault();
    const index = options.indexOf(document.activeElement);
    if (event.key === "ArrowUp" && index <= 0) return input.focus();
    options[event.key === "ArrowDown" ? Math.min(options.length - 1, index + 1) : index - 1].focus();
  }

  input.addEventListener("focus", open);
  input.addEventListener("click", open);
  input.addEventListener("input", open);
  input.parentElement.addEventListener("keydown", event => {
    if (event.key === "Escape" && !menu.hidden) {
      close();
      input.focus();
      return;
    }
    moveFocus(event);
  });
  input.parentElement.addEventListener("focusout", event => {
    if (!input.parentElement.contains(event.relatedTarget)) close();
  });
})();
