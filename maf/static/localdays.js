// Days in your own time zone. The server only knows UTC, so near midnight its "Today" can be your
// "Yesterday" (or tomorrow). This browser redraws days from its own clock instead: the front page's day
// headings and date range, and older times like "Yesterday" or "3 days ago". Your time zone never leaves
// this device (it would hint at which city, and so which class year, you're in).
(function () {
  const DAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
  const MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  const DAY_MS = 86400000;
  const WEEK_DAYS = 7;

  // A local calendar day as "YYYY-MM-DD", and back to a Date at local midnight.
  const dayKey = moment => `${moment.getFullYear()}-${String(moment.getMonth() + 1).padStart(2, "0")}-${String(moment.getDate()).padStart(2, "0")}`;
  const midnight = key => {
    const [year, month, day] = key.split("-").map(Number);
    return new Date(year, month - 1, day);
  };
  // Whole days between two local days (rounded: a daylight-saving day is 23 or 25 hours).
  const daysBetween = (earlier, later) => Math.round((midnight(later) - midnight(earlier)) / DAY_MS);
  const todayKey = () => dayKey(new Date());
  const addDays = (key, count) => {
    const moment = midnight(key);
    moment.setDate(moment.getDate() + count);
    return dayKey(moment);
  };
  const shortDate = moment => `${moment.getDate()} ${MONTH_NAMES[moment.getMonth()].slice(0, 3)}`;

  function dayLabel(key) {
    const ago = daysBetween(key, todayKey());
    if (ago === 0) return "Today";
    if (ago === 1) return "Yesterday";
    const moment = midnight(key);
    return `${DAY_NAMES[moment.getDay()]} ${moment.getDate()} ${MONTH_NAMES[moment.getMonth()]}`;
  }

  // Times older than a day ("Yesterday", "3 days ago", "Friday 20 November"). Newer ones ("2 hours ago")
  // don't depend on the time zone, so the server's words stay.
  function redrawTimes() {
    const now = Date.now();
    for (const time of document.querySelectorAll("time.rel[datetime]")) {
      const moment = new Date(time.getAttribute("datetime"));
      if (Number.isNaN(moment.getTime()) || now - moment < DAY_MS) continue;
      const ago = daysBetween(dayKey(moment), todayKey());
      time.textContent = ago === 1 ? "Yesterday" : ago < WEEK_DAYS ? `${ago} days ago` : dayLabel(dayKey(moment));
    }
  }

  // The front page's 4 days, as days on this device. The latest page ends today; an older one ends on the day
  // its link asked for. The server sends a day either side of its UTC window, so these 4 days are all there.
  const range = document.querySelector(".range[data-start][data-end]");
  const latest = range && !range.querySelector("a.arrow[aria-label='Later 4 days']");
  const windowEnd = range ? (latest ? todayKey() : range.dataset.end) : null;
  const windowStart = windowEnd && addDays(windowEnd, -3);
  const inWindow = key => !range || (key >= windowStart && key <= windowEnd);

  // The front page's 4-day lists: the same posts, regrouped under your days, in the page's order.
  const ORDER = {
    new: (a, b) => (a.dataset.created < b.dataset.created ? 1 : -1),
    old: (a, b) => (a.dataset.created > b.dataset.created ? 1 : -1),
    views: (a, b) => Number(b.dataset.views) - Number(a.dataset.views) || ORDER.new(a, b),
  };

  function regroupDays() {
    const lists = [...document.querySelectorAll("ol.day-list")];
    if (!lists.length) return;
    const order = ORDER[lists[0].dataset.sort] ?? ORDER.new;
    const rows = lists.flatMap(list => [...list.children])
      .filter(row => inWindow(dayKey(new Date(row.dataset.created))))
      .sort(order);
    const groups = new Map();
    for (const row of rows) {
      const key = dayKey(new Date(row.dataset.created));
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(row);
    }
    const anchor = lists[0].previousElementSibling; // the first day's heading: the new ones go where it was
    const parts = [];
    for (const [key, dayRows] of groups) {
      const heading = Object.assign(document.createElement("h2"), { className: "day", textContent: dayLabel(key) });
      const list = Object.assign(document.createElement("ol"), { className: "list day-list" });
      list.dataset.sort = lists[0].dataset.sort;
      list.append(...dayRows);
      parts.push(heading, list);
    }
    anchor.before(...parts);
    for (const list of lists) {
      list.previousElementSibling?.remove();
      list.remove();
    }
  }

  // "23 to 26 November": your 4 days, and arrows that step 4 of them at a time.
  function redrawRange() {
    if (!range) return;
    const start = midnight(windowStart);
    const end = midnight(windowEnd);
    const sameMonth = start.getMonth() === end.getMonth();
    const long = range.querySelector(".long-date");
    const short = range.querySelector(".short-date");
    const month = moment => MONTH_NAMES[moment.getMonth()];
    if (long) long.textContent = sameMonth ? `${start.getDate()} to ${end.getDate()} ${month(end)}` : `${shortDate(start)} to ${shortDate(end)}`;
    if (short) short.textContent = sameMonth ? `${start.getDate()}–${end.getDate()} ${month(end).slice(0, 3)}` : `${shortDate(start)}–${shortDate(end)}`;
    const sort = range.dataset.sort || "new";
    const pageUrl = before => (sort === "new" ? `/?before=${before}` : `/?before=${before}&sort=${sort}`);
    // Back stops at the window holding the first post (its UTC day can be the day before here).
    const first = range.dataset.first;
    setArrow(range.querySelector(".arrow"), first && windowStart >= first ? pageUrl(windowStart) : null, "Earlier 4 days", "‹");
    const reachesToday = addDays(windowEnd, 4) >= todayKey();
    const later = latest ? null : reachesToday && sort === "new" ? "/" : pageUrl(addDays(windowEnd, 5));
    setArrow(range.querySelector(".arrow:last-child"), later, "Later 4 days", "›");
  }

  function setArrow(arrow, href, label, glyph) {
    if (!arrow) return;
    const next = document.createElement(href ? "a" : "span");
    next.className = "arrow";
    next.textContent = glyph;
    if (href) {
      next.href = href;
      next.setAttribute("aria-label", label);
    } else {
      next.setAttribute("aria-disabled", "true");
    }
    arrow.replaceWith(next);
  }

  regroupDays();
  redrawRange();
  redrawTimes();
})();
