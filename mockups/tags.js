// Mockup-only: the # button in the search box opens a list of every hashtag; picking one filters the posts.
// The real app does this on the server with ?tag=<name>.
const tagToggle = document.querySelector(".tag-toggle");
const tagMenu = document.querySelector(".tag-menu");
const searchInput = document.querySelector(".find input");

function countTags() {
  const counts = new Map();
  document.querySelectorAll(".list li[data-tags]").forEach(item => {
    item.dataset.tags.split(" ").forEach(tag => counts.set(tag, (counts.get(tag) ?? 0) + 1));
  });
  return [...counts].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

function filterByTag(tag) {
  searchInput.value = tag ? `#${tag}` : "";
  document.querySelectorAll(".list li").forEach(item => {
    const tags = (item.dataset.tags ?? "").split(" ");
    item.hidden = Boolean(tag) && !tags.includes(tag);
  });
  document.querySelectorAll("h2.day").forEach(heading => {
    const list = heading.nextElementSibling;
    const anyVisible = [...list.children].some(item => !item.hidden);
    heading.hidden = !anyVisible;
    list.hidden = !anyVisible;
  });
  tagMenu.hidden = true;
  tagToggle.setAttribute("aria-expanded", "false");
}

function renderTagMenu() {
  const options = countTags().map(([tag, count]) => {
    const option = document.createElement("button");
    option.type = "button";
    option.innerHTML = `<span>#${tag}</span><span class="tag-count">${count}</span>`;
    option.addEventListener("click", () => filterByTag(tag));
    return option;
  });
  const scroller = Object.assign(document.createElement("div"), { className: "tag-scroll" });
  scroller.append(...options);
  scroller.addEventListener("scroll", updateTagFade);
  tagMenu.replaceChildren(scroller);
}

tagToggle?.addEventListener("click", () => {
  const opening = tagMenu.hidden;
  if (opening) renderTagMenu();
  tagMenu.hidden = !opening;
  tagToggle.setAttribute("aria-expanded", String(opening));
});

document.addEventListener("click", event => {
  if (!tagMenu || tagMenu.hidden || event.target.closest(".find")) return;
  tagMenu.hidden = true;
  tagToggle.setAttribute("aria-expanded", "false");
});

document.querySelectorAll(".meta .tag").forEach(link => {
  link.addEventListener("click", event => {
    event.preventDefault();
    filterByTag(link.textContent.slice(1));
  });
});

// Emptying the search box shows every post again.
searchInput?.addEventListener("input", () => {
  if (searchInput.value.trim() === "") filterByTag(null);
});

// Drop the bottom fade once the list is scrolled to the end (or doesn't need scrolling).
function updateTagFade() {
  const scroller = tagMenu.querySelector(".tag-scroll");
  if (!scroller) return;
  const atEnd = scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight - 2;
  scroller.classList.toggle("at-end", atEnd);
}
tagToggle?.addEventListener("click", () => { if (!tagMenu.hidden) updateTagFade(); });
