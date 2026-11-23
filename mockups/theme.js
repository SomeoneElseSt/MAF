// Light/dark toggle. With no saved choice the page follows the device; a click saves the opposite of what's showing.
const THEME_KEY = "theme";
const toggle = document.querySelector(".theme-toggle");
const prefersDark = window.matchMedia("(prefers-color-scheme: dark)");

function readSavedTheme() {
  try { return localStorage.getItem(THEME_KEY); } catch { return null; }
}

function currentTheme() {
  return readSavedTheme() ?? (prefersDark.matches ? "dark" : "light");
}

function updateLabel() {
  if (!toggle) return;
  toggle.setAttribute("aria-label", currentTheme() === "dark" ? "Switch to light mode" : "Switch to dark mode");
}

toggle?.addEventListener("click", () => {
  const next = currentTheme() === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem(THEME_KEY, next); } catch { /* storage blocked: the choice lasts for this page only */ }
  updateLabel();
});

prefersDark.addEventListener("change", updateLabel);
updateLabel();
