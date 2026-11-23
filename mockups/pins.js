// Personal pins: hovering a post shows a pin; clicking it saves the post in this browser only and moves it into Pinned.
// Nothing is sent to the server, so MAF never learns what anyone saved.
const STORAGE_KEY = "maf.pins";
const PIN_ICON = `<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="M5.5 1.5h5l-.8 4.2 2.8 2.8v1h-4v5l-.5.5-.5-.5v-5h-4v-1l2.8-2.8z" fill="var(--pin-fill)" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/></svg>`;

const pinnedList = document.querySelector(".pinned-list");
const pinnedHeading = pinnedList.previousElementSibling;
const announcer = document.getElementById("pin-status");
const homes = new Map();

function readPins() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY)) ?? []; } catch { return []; }
}

function writePins(keys) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(keys)); } catch {}
}

const keyOf = row => row.querySelector(".title").getAttribute("href") + "|" + row.querySelector(".title").textContent;

// Day groups with nothing left in them (and Pinned with nothing in it) are hidden.
function refreshGroups() {
  document.querySelectorAll("ol.list").forEach(list => {
    const empty = list.children.length === 0;
    list.hidden = empty;
    list.previousElementSibling.hidden = empty;
  });
}

function moveToPinned(row) {
  // Your pins go after the maintainer's, most recently pinned first.
  const lastFixed = [...pinnedList.querySelectorAll("li.fixed")].pop();
  lastFixed ? lastFixed.after(row) : pinnedList.prepend(row);
}

// Back to its own day, in its original position among the rows still there.
function moveHome(row) {
  const { list, order } = homes.get(row);
  const later = order.slice(order.indexOf(row) + 1).find(other => other.parentElement === list);
  later ? list.insertBefore(row, later) : list.append(row);
}

function setPinned(row, pinned) {
  const button = row.querySelector(".pin");
  button.setAttribute("aria-pressed", String(pinned));
  button.setAttribute("aria-label", pinned ? "Unpin" : "Pin to top");
  row.classList.toggle("is-pinned", pinned);
}

function togglePin(row) {
  const key = keyOf(row);
  const pins = readPins();
  const pinning = !pins.includes(key);
  writePins(pinning ? [key, ...pins] : pins.filter(other => other !== key));
  setPinned(row, pinning);
  pinning ? moveToPinned(row) : moveHome(row);
  refreshGroups();
  row.querySelector(".pin").focus();
  announcer.textContent = pinning ? "Pinned to the top. Only you can see this." : "Unpinned.";
}

document.querySelectorAll("ol.list:not(.pinned-list)").forEach(list => {
  const order = [...list.children];
  order.forEach(row => {
    homes.set(row, { list, order });
    const button = document.createElement("button");
    button.type = "button";
    button.className = "pin";
    button.innerHTML = PIN_ICON;
    button.addEventListener("click", () => togglePin(row));
    row.append(button);
    setPinned(row, false);
  });
});

// Restore saved pins, oldest first so the newest ends up on top.
const rowsByKey = new Map([...homes.keys()].map(row => [keyOf(row), row]));
readPins().slice().reverse().forEach(key => {
  const row = rowsByKey.get(key);
  if (!row) return;
  setPinned(row, true);
  moveToPinned(row);
});
refreshGroups();
