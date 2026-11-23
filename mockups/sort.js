// Mockup-only: applies ?sort=new|old|views to the static front page by reordering the posts in the browser.
// The real app sorts on the server; this just lets the UX be tried.
const SORT_OPTIONS = [["new", "Newest"], ["old", "Oldest"], ["views", "Most viewed"]];
const params = new URLSearchParams(location.search);
const sortMode = SORT_OPTIONS.some(([key]) => key === params.get("sort")) ? params.get("sort") : "new";

function urlWithSort(href, mode) {
  const url = new URL(href, location.href);
  if (mode === "new") url.searchParams.delete("sort");
  else url.searchParams.set("sort", mode);
  return url.pathname.split("/").pop() + url.search;
}

function renderSortBar() {
  const bar = document.querySelector(".sort");
  if (!bar) return;
  bar.replaceChildren(Object.assign(document.createElement("span"), { textContent: "Sort by:" }));
  for (const [key, label] of SORT_OPTIONS) {
    const option = key === sortMode ? document.createElement("strong") : document.createElement("a");
    option.textContent = label;
    option.dataset.text = label;
    if (key !== sortMode) option.href = urlWithSort(startPageFor(key), key);
    bar.append(option);
  }
}

// Oldest starts at the first page ever; Newest and Most viewed start at the latest one.
function startPageFor(mode) {
  return mode === "old" ? PAGES[0].file : PAGES.at(-1).file;
}

function arrowElement(page, glyph, label) {
  if (!page) return Object.assign(document.createElement("span"), { className: "arrow", textContent: glyph, ariaHidden: "true" });
  const link = Object.assign(document.createElement("a"), { className: "arrow", textContent: glyph, href: urlWithSort(page.file, sortMode) });
  link.setAttribute("aria-label", label);
  return link;
}

function renderRange() {
  const range = document.querySelector(".range");
  const currentFile = location.pathname.split("/").pop() || "index.html";
  const index = PAGES.findIndex(page => page.file === currentFile);
  if (!range || index === -1) return;
  const dates = Object.assign(document.createElement("span"), { textContent: PAGES.at(index).range });
  range.replaceChildren(arrowElement(PAGES.at(index - 1) && index > 0 ? PAGES.at(index - 1) : null, "‹", "Earlier posts"), dates, arrowElement(PAGES.at(index + 1) ?? null, "›", "Later posts"));
}

function reverseDays() {
  const days = [...document.querySelectorAll("h2.day")];
  const anchor = days.at(-1).nextElementSibling.nextElementSibling;
  for (const heading of days.reverse()) {
    const list = heading.nextElementSibling;
    list.append(...[...list.children].reverse());
    anchor.before(heading, list);
  }
}

function flattenByViews() {
  const days = [...document.querySelectorAll("h2.day")];
  const items = [...document.querySelectorAll(".list li")];
  items.sort((a, b) => Number(b.dataset.views) - Number(a.dataset.views));
  for (const item of items) {
    const meta = item.querySelector(".meta");
    meta.prepend(`${item.dataset.day}, `);
  }
  const merged = document.createElement("ol");
  merged.className = "list list-flat";
  merged.append(...items);
  days[0].before(merged);
  days.forEach(heading => { heading.nextElementSibling.remove(); heading.remove(); });
}

renderSortBar();
renderRange();
if (sortMode === "old") reverseDays();
if (sortMode === "views") flattenByViews();
