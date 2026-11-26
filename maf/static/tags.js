// The # button in the search box opens every hashtag with its post count; picking
// one filters the posts in place. The list comes from the server as JSON in
// <script id="tag-data">, so counts match the whole site, not just this page.
// Without JS the button is a plain link to /tags.
const tagToggle = document.querySelector(".tag-toggle");
const tagMenu = document.querySelector(".tag-menu");
const searchInput = document.querySelector(".find input");
const tagData = document.getElementById("tag-data");
const ALL_TAGS = tagData ? JSON.parse(tagData.textContent) : [];
const SCROLL_STEP = 128;
const CHEVRON_UP = '<svg viewBox="0 0 16 10" width="14" height="9" aria-hidden="true"><path d="M2 8l6-6 6 6" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';
const CHEVRON_DOWN = '<svg viewBox="0 0 16 10" width="14" height="9" aria-hidden="true"><path d="M2 2l6 6 6-6" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';

// Tags open on the board this page belongs to (/ or /dating/), whose tags the menu lists.
const TAG_BASE = tagData?.dataset.base || "/";

function goToTag(tag) {
  window.location.assign(tag ? `${TAG_BASE}?tag=${encodeURIComponent(tag)}` : TAG_BASE);
}

function scrollArrow(direction, scroller) {
  const arrow = Object.assign(document.createElement("button"), { type: "button", className: `tag-more ${direction}` });
  arrow.innerHTML = direction === "up" ? CHEVRON_UP : CHEVRON_DOWN;
  arrow.setAttribute("aria-label", direction === "up" ? "Scroll up" : "Scroll down");
  arrow.addEventListener("click", () => scroller.scrollBy({ top: direction === "up" ? -SCROLL_STEP : SCROLL_STEP, behavior: "smooth" }));
  return arrow;
}

// Shared with the Feed list (bell.js), which scrolls the same way.
function updateTagFade(menu = tagMenu) {
  const scroller = menu.querySelector(".tag-scroll");
  if (!scroller) return;
  menu.classList.toggle("more-above", scroller.scrollTop > 2);
  menu.classList.toggle("more-below", scroller.scrollTop + scroller.clientHeight < scroller.scrollHeight - 2);
}

function renderTagMenu() {
  const options = ALL_TAGS.map(([tag, count]) => {
    const option = document.createElement("button");
    option.type = "button";
    option.innerHTML = `<span>#${tag}</span><span class="tag-count">${count}</span>`;
    option.addEventListener("click", () => goToTag(tag));
    return option;
  });
  const scroller = Object.assign(document.createElement("div"), { className: "tag-scroll" });
  scroller.append(...options);
  scroller.addEventListener("scroll", updateTagFade);
  tagMenu.replaceChildren(scrollArrow("up", scroller), scroller, scrollArrow("down", scroller));
}

function arrowKeys(event) {
  if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
  const options = [...tagMenu.querySelectorAll(".tag-scroll button")];
  const index = options.indexOf(document.activeElement);
  event.preventDefault();
  const next = options[event.key === "ArrowDown" ? Math.min(options.length - 1, index + 1) : Math.max(0, index - 1)];
  (next ?? options[0])?.focus();
}

tagToggle?.addEventListener("click", () => {
  const opening = tagMenu.hidden;
  if (opening) renderTagMenu();
  tagMenu.hidden = !opening;
  tagToggle.setAttribute("aria-expanded", String(opening));
  if (opening) {
    updateTagFade();
    tagMenu.querySelector(".tag-scroll button")?.focus();
  }
});

document.addEventListener("keydown", event => {
  if (tagMenu?.hidden) return;
  if (event.key === "Escape") {
    tagMenu.hidden = true;
    tagToggle.setAttribute("aria-expanded", "false");
    tagToggle.focus();
    return;
  }
  arrowKeys(event);
});

document.addEventListener("click", event => {
  if (!tagMenu || tagMenu.hidden || event.target.closest(".find")) return;
  tagMenu.hidden = true;
  tagToggle.setAttribute("aria-expanded", "false");
});

searchInput?.addEventListener("keydown", event => {
  if (event.key !== "Enter" || !searchInput.value.trim().startsWith("#")) return;
  event.preventDefault();
  goToTag(searchInput.value.trim().slice(1).toLowerCase());
});
