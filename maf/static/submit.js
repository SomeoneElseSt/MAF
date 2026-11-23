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
