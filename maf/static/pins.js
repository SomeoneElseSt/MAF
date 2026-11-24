// Personal pins. Every post in a list (front page, search, tag pages) gets a pin button. Pinned posts are saved in
// this browser only and shown in Pinned on the front page (Newest, latest page). Nothing is sent to the server.
const STORAGE_KEY = "maf.pins";
const PIN_ICON = `<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="M5.5 1.5h5l-.8 4.2 2.8 2.8v1h-4v5l-.5.5-.5-.5v-5h-4v-1l2.8-2.8z" fill="var(--pin-fill)" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/></svg>`;

const pinnedList = document.querySelector(".pinned-list");
const announcer = document.getElementById("pin-status");
const hotTags = (pinnedList?.dataset.hotTags ?? "").split(" ").filter(Boolean);
const homes = new Map();

// Saved pins: [{id, title, host, tags}], most recently pinned first.
function readPins() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
    return Array.isArray(saved) ? saved.filter(pin => pin && pin.id) : [];
  } catch {
    return [];
  }
}

function writePins(pins) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(pins)); } catch {}
}

const snapshotOf = row => ({
  id: row.dataset.id,
  title: row.dataset.title,
  host: row.dataset.host ?? "",
  tags: (row.dataset.tags ?? "").split(" ").filter(Boolean),
});

function setPinned(row, pinned) {
  const button = row.querySelector(".pin");
  button.setAttribute("aria-pressed", String(pinned));
  button.setAttribute("aria-label", pinned ? "Unpin" : "Pin to top");
  row.classList.toggle("is-pinned", pinned);
}

function addPinButton(row) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "pin";
  button.innerHTML = PIN_ICON;
  button.addEventListener("click", () => togglePin(row));
  row.append(button);
}

// A pinned post that isn't on this page is drawn from its saved snapshot.
function rowFromSnapshot(pin) {
  const row = document.createElement("li");
  Object.assign(row.dataset, { id: pin.id, title: pin.title, host: pin.host, tags: pin.tags.join(" ") });
  if (pin.tags.some(tag => hotTags.includes(tag))) row.classList.add("hot");
  const title = Object.assign(document.createElement("a"), { className: "title", href: `/thread/${pin.id}`, textContent: pin.title });
  row.append(title);
  if (pin.host) row.append(Object.assign(document.createElement("span"), { className: "host", textContent: `(${pin.host})` }));
  const meta = Object.assign(document.createElement("div"), { className: "meta", textContent: "Pinned by you" });
  pin.tags.forEach((tag, index) => {
    meta.append(index === 0 ? " · " : ", ");
    const link = Object.assign(document.createElement("a"), { className: "tag", href: `/?tag=${encodeURIComponent(tag)}`, textContent: `#${tag}` });
    if (hotTags.includes(tag)) link.classList.add("hot-tag");
    meta.append(link);
  });
  row.append(meta);
  addPinButton(row);
  return row;
}

// Hide day groups (and Pinned) that have nothing left in them.
function refreshGroups() {
  document.querySelectorAll("ol.list").forEach(list => {
    const empty = list.children.length === 0;
    list.hidden = empty;
    if (list.previousElementSibling?.matches("h2.day")) list.previousElementSibling.hidden = empty;
  });
}

// Your pins go after the maintainer's, most recently pinned first.
function moveToPinned(row) {
  const lastFixed = [...pinnedList.querySelectorAll("li.fixed")].pop();
  lastFixed ? lastFixed.after(row) : pinnedList.prepend(row);
}

// Back to where it was on this page, or gone if it only came from storage.
function moveHome(row) {
  const home = homes.get(row);
  if (!home) return row.remove();
  const later = home.order.slice(home.order.indexOf(row) + 1).find(other => other.parentElement === home.list);
  later ? home.list.insertBefore(row, later) : home.list.append(row);
}

function togglePin(row) {
  const pins = readPins();
  const pinning = !pins.some(pin => pin.id === row.dataset.id);
  writePins(pinning ? [snapshotOf(row), ...pins] : pins.filter(pin => pin.id !== row.dataset.id));
  setPinned(row, pinning);
  if (pinnedList) {
    pinning ? moveToPinned(row) : moveHome(row);
    refreshGroups();
  }
  if (row.isConnected) row.querySelector(".pin").focus();
  const where = pinnedList ? "Pinned to the top." : "Pinned to the top of the front page.";
  announcer.textContent = pinning ? `${where} Only you can see this.` : "Unpinned.";
}

// Posts only: comment hits in search have no title to save.
document.querySelectorAll("ol.list:not(.pinned-list)").forEach(list => {
  const order = [...list.children].filter(row => row.dataset.id && row.dataset.title);
  order.forEach(row => {
    homes.set(row, { list, order });
    addPinButton(row);
    setPinned(row, false);
  });
});

const rowsById = new Map([...homes.keys()].map(row => [row.dataset.id, row]));
const fixedIds = new Set([...document.querySelectorAll(".pinned-list li.fixed")].map(row => row.dataset.id));
// Oldest first, so the most recent pin ends up on top.
readPins().slice().reverse().forEach(pin => {
  const row = rowsById.get(pin.id);
  if (row) setPinned(row, true);
  if (!pinnedList || fixedIds.has(pin.id)) return;
  const pinnedRow = row ?? rowFromSnapshot(pin);
  setPinned(pinnedRow, true);
  moveToPinned(pinnedRow);
});
if (pinnedList) refreshGroups();
