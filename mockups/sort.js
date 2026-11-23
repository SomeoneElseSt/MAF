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
    if (key !== sortMode) option.href = urlWithSort(location.href, key);
    bar.append(option);
  }
}

function keepSortOnPageLinks() {
  document.querySelectorAll(".pager a, .range a").forEach(link => {
    link.href = urlWithSort(link.getAttribute("href"), sortMode);
  });
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
keepSortOnPageLinks();
if (sortMode === "old") reverseDays();
if (sortMode === "views") flattenByViews();
