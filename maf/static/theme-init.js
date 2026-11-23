// Applies the saved theme before the page paints, so there is no flash. Loaded in <head>, not deferred.
try { const saved = localStorage.getItem("theme"); if (saved) document.documentElement.dataset.theme = saved; } catch {}
