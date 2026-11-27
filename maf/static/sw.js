// Alerts (served at /sw.js so it covers the whole site). It only shows what the server sent: what happened
// ("New reply to your post"), never anyone's words. Tapping an alert opens the reply it's about.
self.addEventListener("push", event => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = {};
  }
  event.waitUntil(self.registration.showNotification(data.title || "MAF", {
    body: data.body || "Something new in your Feed",
    icon: "/static/icon-180.png",
    tag: data.tag, // more replies on the same post replace the alert instead of piling up
    renotify: Boolean(data.tag),
    data: { url: data.url || "/" },
  }));
});

self.addEventListener("notificationclick", event => {
  event.notification.close();
  const url = new URL(event.notification.data?.url || "/", self.location.origin).href;
  event.waitUntil(openOrFocus(url));
});

async function openOrFocus(url) {
  const windows = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
  const open = windows.find(client => client.url.startsWith(self.location.origin));
  if (!open) return self.clients.openWindow(url);
  try {
    await open.navigate(url);
    return open.focus();
  } catch {
    return self.clients.openWindow(url); // a tab this worker doesn't control can't be sent elsewhere
  }
}
