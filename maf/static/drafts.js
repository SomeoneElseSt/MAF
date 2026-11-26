// Keeps unfinished posts and replies in this browser, so a reload, a crash or the server
// being down doesn't lose them. Nothing is sent anywhere; drafts are cleared once they post.
(function () {
  const STORAGE_KEY = "maf.drafts";
  const SENT_KEY = "maf.sent";
  const DRAFT_DAYS = 7;
  const SENT_WINDOW_MS = 60 * 1000;
  const DAY_MS = 24 * 60 * 60 * 1000;

  function read(storage, key, fallback) {
    try {
      return JSON.parse(storage.getItem(key)) || fallback;
    } catch {
      return fallback;
    }
  }

  function write(storage, key, value) {
    try {
      if (value === null) storage.removeItem(key);
      else storage.setItem(key, JSON.stringify(value));
    } catch {
      // Storage off or full: drafts just aren't kept.
    }
  }

  const drafts = read(localStorage, STORAGE_KEY, {});
  const now = Date.now();
  for (const [key, draft] of Object.entries(drafts)) {
    if (now - draft.saved > DRAFT_DAYS * DAY_MS) delete drafts[key];
  }

  // A post or reply that went through lands on its thread with no notice: its draft is done.
  const sent = read(sessionStorage, SENT_KEY, null);
  write(sessionStorage, SENT_KEY, null);
  const navigation = performance.getEntriesByType("navigation")[0];
  const arrivedFresh = !navigation || navigation.type === "navigate";
  const landedOk = /^(\/nsfw|\/dates)?\/thread\//.test(location.pathname) && !new URLSearchParams(location.search).has("notice");
  if (sent && arrivedFresh && landedOk && now - sent.at < SENT_WINDOW_MS) delete drafts[sent.key];
  write(localStorage, STORAGE_KEY, drafts);

  function draftKey(form) {
    if (form.getAttribute("action") === "/submit") return "submit";
    if (form.getAttribute("action") === "/edit") return `edit:${form.querySelector("input[name='item_id']").value}`;
    const parent = form.querySelector("input[name='parent_id']");
    return parent ? `comment:${parent.value}` : null;
  }

  function openBox(form) {
    if (!form.classList.contains("inline-reply")) return;
    form.hidden = false;
    document.querySelector(`[aria-controls="${form.id}"]`)?.setAttribute("aria-expanded", "true");
  }

  function setUp(form) {
    const key = draftKey(form);
    const fields = [...form.querySelectorAll("textarea, input[type='text'], input[type='url']")];
    if (!key || !fields.length) return;
    const names = fields.map(field => field.name);

    const saved = drafts[key];
    if (saved) {
      fields.forEach((field, i) => {
        if (field.value || !saved.fields[names[i]]) return;
        field.value = saved.fields[names[i]];
        field.dispatchEvent(new Event("input", { bubbles: true }));
      });
      openBox(form);
    }

    // Coming back with Back or Forward, or reloading, the browser refills boxes with whatever they
    // held when you left, even text that was sent. A box with no saved draft has nothing unsent: it goes
    // back to what the page sent (empty for a reply, the item's current words for an edit).
    window.addEventListener("pageshow", event => {
      const navigation = performance.getEntriesByType("navigation")[0]?.type;
      const returning = event.persisted || navigation === "back_forward" || navigation === "reload";
      if (!returning || read(localStorage, STORAGE_KEY, {})[key]) return;
      fields.forEach(field => {
        if (field.value === field.defaultValue) return;
        field.value = field.defaultValue;
        field.dispatchEvent(new Event("input", { bubbles: true }));
      });
    });

    form.addEventListener("input", () => {
      const values = Object.fromEntries(fields.map((field, i) => [names[i], field.value]));
      const empty = Object.values(values).every(value => !value.trim());
      if (empty) delete drafts[key];
      else drafts[key] = { fields: values, saved: Date.now() };
      write(localStorage, STORAGE_KEY, drafts);
    });
  }

  document.querySelectorAll("form[action='/submit'], form[action='/comment'], form[action='/edit']").forEach(form => {
    setUp(form);
    form.addEventListener("submit", () => {
      const key = draftKey(form);
      if (key) write(sessionStorage, SENT_KEY, { key, at: Date.now() });
    });
    // Sent in the background and saved (replies.js): the page reloads rather than arriving fresh,
    // so the check above can't tell it went through. Drop the draft now.
    form.addEventListener("maf:sent", () => {
      const key = draftKey(form);
      if (!key) return;
      const saved = read(localStorage, STORAGE_KEY, {});
      delete saved[key];
      write(localStorage, STORAGE_KEY, saved);
    });
  });
})();
