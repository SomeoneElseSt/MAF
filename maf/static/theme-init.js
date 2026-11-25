// Applies the saved theme before the page paints, so there is no flash. Loaded in <head>, not deferred.
try { const saved = localStorage.getItem("theme"); if (saved) document.documentElement.dataset.theme = saved; } catch {}

// The tab icon follows the theme. Called again by theme.js when the theme changes.
function setThemeIcon() {
  const icon = document.querySelector("link[rel=icon][data-light]");
  if (!icon) return;
  const chosen = document.documentElement.dataset.theme;
  const dark = chosen ? chosen === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
  icon.href = dark ? icon.dataset.dark : icon.dataset.light;
}
setThemeIcon();
