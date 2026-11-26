// The NSFW word in the header. Where it leads is decided on the server (navigation.py); links that turn NSFW
// on go through /?side=nsfw. The first time one does in this browser, a warning asks first.
(function () {
  const dialog = document.getElementById("nsfw-dialog");
  if (!dialog) return;
  const COOKIE = "maf_nsfw";
  const WARNED_KEY = "maf.nsfw-warned";
  let destination = null;

  function warned() {
    try {
      return localStorage.getItem(WARNED_KEY) === "1";
    } catch {
      return false; // storage off: it asks each time, which errs on the safe side
    }
  }

  document.addEventListener("click", event => {
    const link = event.target.closest('a[href*="side=nsfw"]');
    if (!link || warned()) return;
    event.preventDefault();
    destination = link.href;
    dialog.showModal();
  });
  dialog.querySelector("[data-nsfw-yes]").addEventListener("click", () => {
    try {
      localStorage.setItem(WARNED_KEY, "1");
    } catch {
      // storage off: it'll ask again next time
    }
    dialog.close();
    location.href = destination;
  });
  dialog.querySelector("[data-nsfw-no]").addEventListener("click", () => dialog.close());

  // Back to a page from before a switch (e.g. turned on in another tab): show this page for the current side.
  // (Opening the Dates page turns NSFW off, so there the word and the setting always agree too.)
  const toggle = document.querySelector(".nsfw-toggle");
  window.addEventListener("pageshow", () => {
    if (!toggle) return;
    const isOn = document.cookie.split("; ").includes(`${COOKIE}=1`);
    if (toggle.hasAttribute("data-on") !== isOn) location.reload();
  });
})();
