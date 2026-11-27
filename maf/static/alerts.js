// Alerts on this device (web push). Right after you post, reply, subscribe, or post or send a Dates profile, a
// grey note under it asks once whether this device should alert you. One yes covers everything your Feed gets,
// except reactions. "Not now" waits a week before asking again. iPhones only alert for sites on the Home Screen,
// so there the note explains that step (only after you tap Turn on alerts). The bottom of the Feed menu shows
// whether alerts are on here and turns them on or off. Alerts say what happened, never anyone's words.
(function () {
  const key = document.body.dataset.pushKey;
  if (!key) return; // alerts are off on this server

  const ASK_KEY = "maf.alerts-ask"; // what you just did, kept across the reload that shows it
  const NOT_NOW_KEY = "maf.alerts-not-now";
  const ASK_WINDOW_MS = 5 * 60 * 1000;
  const NOT_NOW_MS = 7 * 24 * 60 * 60 * 1000;
  const REFRESH_KEY = "maf.alerts-refreshed";
  const REFRESH_MS = 24 * 60 * 60 * 1000;
  const QUESTIONS = {
    post: "Get an alert when someone replies to your post?",
    comment: "Get an alert when someone replies to your comment?",
    subscribe: "Get alerts when there's new activity on this post?",
    profile: "Get an alert when someone sends you their profile?",
    sent: "Get an alert if they match with you?",
    message: "Get an alert when they reply?",
  };
  const BLOCKED = "Alerts are blocked for maforum.net in this browser's settings.";
  const SHARE_ICON = '<svg class="share-icon" viewBox="0 0 17 22" aria-label="Share" role="img"><path d="M5.5 8H3.5a2 2 0 0 0-2 2v8.5a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V10a2 2 0 0 0-2-2h-2"/><path d="M8.5 13.5V1.5"/><path d="M4.8 5 8.5 1.3 12.2 5"/></svg>';
  const HOME_SCREEN_STEPS = `<ol class="alert-steps"><li>Tap Share ${SHARE_ICON} in Safari.</li><li>Tap <b>Add to Home Screen</b>.</li><li>Open MAF from your Home Screen and turn alerts on there.</li></ol>`;

  const supported = "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
  const iphone = /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const installed = matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
  const needsHomeScreen = iphone && !installed;

  function read(name) {
    try {
      return localStorage.getItem(name);
    } catch {
      return null;
    }
  }

  function write(name, value) {
    try {
      localStorage.setItem(name, value);
    } catch {
      // Storage off: "Not now" just isn't remembered.
    }
  }

  async function currentSubscription() {
    if (!supported) return null;
    const registration = await navigator.serviceWorker.getRegistration("/");
    return registration ? registration.pushManager.getSubscription() : null;
  }

  function keyBytes() {
    const base64 = (key + "=".repeat((4 - (key.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/");
    return Uint8Array.from(atob(base64), c => c.charCodeAt(0));
  }

  function post(path, values) {
    return fetch(path, { method: "POST", body: new URLSearchParams(values) });
  }

  async function tellServer(subscription) {
    const { endpoint, keys } = subscription.toJSON();
    const response = await post("/push/subscribe", { endpoint, p256dh: keys.p256dh, auth: keys.auth });
    return response.ok;
  }

  // Returns what to say afterwards: "on", "blocked", "home-screen", or "failed".
  async function turnOn() {
    if (needsHomeScreen) return "home-screen";
    if (!supported) return "failed";
    try {
      await navigator.serviceWorker.register("/sw.js");
      const permission = await Notification.requestPermission();
      const registration = await navigator.serviceWorker.ready; // a new worker must be running to subscribe
      if (permission === "denied") return "blocked";
      if (permission !== "granted") return "failed";
      const subscription = await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes() });
      return (await tellServer(subscription)) ? "on" : "failed";
    } catch {
      return "failed";
    }
  }

  async function turnOff() {
    const subscription = await currentSubscription();
    if (!subscription) return;
    await post("/push/unsubscribe", { endpoint: subscription.endpoint });
    await subscription.unsubscribe();
  }

  // The note under what you just did ---------------------------------------------------------------------

  function remember(kind) {
    try {
      sessionStorage.setItem(ASK_KEY, JSON.stringify({ kind, at: Date.now(), path: location.pathname }));
    } catch {
      // Storage off: no note this time.
    }
  }

  function recall() {
    try {
      return JSON.parse(sessionStorage.getItem(ASK_KEY) || "null");
    } catch {
      return null;
    }
  }

  function forget() {
    try {
      sessionStorage.removeItem(ASK_KEY);
    } catch {
      // nothing to forget
    }
  }

  const onDates = document.body.dataset.board === "dates";
  document.addEventListener("submit", event => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || form.matches(".edit-in-place")) return;
    const action = form.getAttribute("action");
    if (action === "/submit") return remember("post");
    if (action === "/dates/submit") return remember("profile");
    if (form.id === "subscribe-form" && document.querySelector(".subscribe[aria-pressed='false']")) return remember("subscribe");
    if (action !== "/comment") return;
    const inReply = Boolean(form.closest("li.comment"));
    if (onDates) return remember(inReply ? "message" : "sent");
    remember("comment");
  }, true);

  // Where the note goes for what you just did, or nothing if this page isn't the result of it.
  function placeFor(ask) {
    if (new URLSearchParams(location.search).has("notice")) return null; // it didn't go through
    const post = document.querySelector("article.post-head");
    if (ask.kind === "post" || ask.kind === "profile") return post?.matches("[data-mine]") ? post : null;
    if (ask.kind === "subscribe") {
      const subscribed = document.querySelector(".subscribe[aria-pressed='true']");
      return ask.path === location.pathname && subscribed ? document.getElementById("comment-form") : null;
    }
    const reply = location.hash && document.getElementById(decodeURIComponent(location.hash.slice(1)));
    if (!reply?.matches?.("li.comment[data-mine]")) return null;
    return reply.querySelector(":scope > .actions") || reply.querySelector(":scope > .meta");
  }

  function note(html) {
    const box = Object.assign(document.createElement("div"), { className: "notice alert-ask" });
    box.innerHTML = html;
    return box;
  }

  function settle(box, outcome) {
    if (outcome === "on") box.innerHTML = "<p>Alerts are on for this device. You can turn them off at the bottom of the Feed menu.</p>";
    if (outcome === "blocked") box.innerHTML = `<p>${BLOCKED}</p>`;
    if (outcome === "failed") box.innerHTML = "<p>Couldn't turn on alerts on this device. Try again later from the Feed menu.</p>";
    if (outcome === "home-screen") box.innerHTML = `<p>On iPhone, alerts need MAF on your Home Screen:</p>${HOME_SCREEN_STEPS}<div class="row"><button class="button plain" type="button" data-alert-done>Got it</button></div>`;
    box.querySelector("[data-alert-done]")?.addEventListener("click", () => box.remove());
  }

  async function maybeAsk() {
    const ask = recall();
    if (!ask || Date.now() - ask.at > ASK_WINDOW_MS || !QUESTIONS[ask.kind]) return;
    const place = placeFor(ask);
    if (!place) return;
    forget();
    if (!supported && !needsHomeScreen) return;
    if (supported && Notification.permission === "denied") return;
    if (Date.now() - Number(read(NOT_NOW_KEY) || 0) < NOT_NOW_MS) return;
    if (await currentSubscription()) return;
    const box = note(`<p>${QUESTIONS[ask.kind]}</p>
      <div class="row"><button class="button" type="button" data-alert-on>Turn on alerts</button><button class="button plain" type="button" data-alert-later>Not now</button></div>`);
    box.querySelector("[data-alert-on]").addEventListener("click", async () => settle(box, await turnOn()));
    box.querySelector("[data-alert-later]").addEventListener("click", () => {
      write(NOT_NOW_KEY, String(Date.now()));
      box.remove();
    });
    place.after(box);
  }

  // The bottom of the Feed menu ---------------------------------------------------------------------------

  async function feedLine(line) {
    if (needsHomeScreen) {
      line.innerHTML = `Alerts on iPhone need MAF on your Home Screen. <button class="linkish" type="button" data-alert-how>How?</button>`;
      line.querySelector("[data-alert-how]").addEventListener("click", event => {
        event.stopPropagation();
        line.innerHTML = `Alerts on iPhone need MAF on your Home Screen:${HOME_SCREEN_STEPS}`;
      });
      return;
    }
    if (!supported) return line.remove();
    if (Notification.permission === "denied") {
      line.textContent = BLOCKED;
      return;
    }
    const on = Boolean(await currentSubscription());
    line.innerHTML = `Alerts on this device: ${on ? "on" : "off"} · <button class="linkish" type="button">${on ? "Turn off" : "Turn on"}</button>`;
    line.querySelector("button").addEventListener("click", async event => {
      event.stopPropagation();
      line.textContent = on ? "Turning off…" : "Turning on…";
      if (on) await turnOff();
      const outcome = on ? "off" : await turnOn();
      if (outcome === "blocked") line.textContent = BLOCKED;
      else if (outcome === "failed") line.textContent = "Couldn't turn on alerts on this device. Try again later.";
      else feedLine(line);
    });
  }

  document.addEventListener("maf:feed-menu", event => {
    const line = Object.assign(document.createElement("div"), { className: "bell-alerts" });
    event.detail.append(line);
    feedLine(line);
  });

  // A device with alerts on tells the server once a day, so its alerts follow this pass (signing in again
  // gives a new one).
  async function refresh() {
    if (Date.now() - Number(read(REFRESH_KEY) || 0) < REFRESH_MS) return;
    const subscription = await currentSubscription();
    if (!subscription || Notification.permission !== "granted") return;
    if (await tellServer(subscription)) write(REFRESH_KEY, String(Date.now()));
  }

  maybeAsk();
  refresh();
})();
