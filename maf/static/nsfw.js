// The NSFW switch in the header. On, lists show only NSFW posts; off, only the rest. It's a setting for
// this browser (a cookie the server reads to pick the list), like Dark. The first time it's turned on
// here, a warning asks first; after that it switches straight away. The page's colour follows what's on it
// (an NSFW post stays tinted either way), so on a post the switch only changes where lists take you.
(function () {
  const toggle = document.querySelector(".nsfw-toggle");
  const dialog = document.getElementById("nsfw-dialog");
  if (!toggle || !dialog) return;
  const COOKIE = "maf_nsfw";
  const WARNED_KEY = "maf.nsfw-warned";
  const YEAR_SECONDS = 31536000;

  const isOn = () => document.cookie.split("; ").includes(`${COOKIE}=1`);

  function warned() {
    try {
      return localStorage.getItem(WARNED_KEY) === "1";
    } catch {
      return false; // storage off: it asks each time, which errs on the safe side
    }
  }

  function switchTo(on) {
    const secure = location.protocol === "https:" ? "; secure" : "";
    document.cookie = `${COOKIE}=${on ? 1 : 0}; path=/; max-age=${YEAR_SECONDS}; samesite=lax${secure}`;
    toggle.setAttribute("aria-pressed", String(on));
    location.reload(); // lists, counts and the # menu all come from the server for the side you're on
  }

  toggle.addEventListener("click", () => {
    const turningOn = !isOn();
    if (turningOn && !warned()) {
      dialog.showModal();
      return;
    }
    switchTo(turningOn);
  });
  dialog.querySelector("[data-nsfw-yes]").addEventListener("click", () => {
    try {
      localStorage.setItem(WARNED_KEY, "1");
    } catch {
      // storage off: it'll ask again next time
    }
    dialog.close();
    switchTo(true);
  });
  dialog.querySelector("[data-nsfw-no]").addEventListener("click", () => dialog.close());

  // Back to a page from before a switch (e.g. turned on in another tab): show this page for the current side.
  window.addEventListener("pageshow", () => {
    if ((toggle.getAttribute("aria-pressed") === "true") !== isOn()) location.reload();
  });
})();
