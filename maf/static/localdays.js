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
    const rows = lists.flatMap(list => [...list.children]).sort(order);
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

  // "23 to 26 November": the local days this page's UTC window covers (up to now, on the latest page).
  function redrawRange() {
    const range = document.querySelector(".range[data-start][data-end]");
    if (!range) return;
    const start = new Date(`${range.dataset.start}T00:00:00Z`);
    const after = new Date(new Date(`${range.dataset.end}T00:00:00Z`).getTime() + DAY_MS - 1);
    const end = after > new Date() ? new Date() : after;
    const sameMonth = start.getMonth() === end.getMonth();
    const long = range.querySelector(".long-date");
    const short = range.querySelector(".short-date");
    const month = moment => MONTH_NAMES[moment.getMonth()];
    if (long) long.textContent = sameMonth ? `${start.getDate()} to ${end.getDate()} ${month(end)}` : `${shortDate(start)} to ${shortDate(end)}`;
    if (short) short.textContent = sameMonth ? `${start.getDate()}–${end.getDate()} ${month(end).slice(0, 3)}` : `${shortDate(start)}–${shortDate(end)}`;
  }

  regroupDays();
  redrawRange();
  redrawTimes();
})();
