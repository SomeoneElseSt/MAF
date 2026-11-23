// A Copy button on every code box (Use this data). Shows "Copied" for a moment after copying.
(function () {
  const RESET_MS = 1600;
  document.querySelectorAll(".prose pre").forEach(box => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "copy";
    button.textContent = "Copy";
    button.setAttribute("aria-label", "Copy this code");
    button.addEventListener("click", async () => {
      const text = box.querySelector("code")?.innerText ?? box.innerText;
      try {
        await navigator.clipboard.writeText(text);
        button.textContent = "Copied";
      } catch {
        button.textContent = "Press Cmd+C";
      }
      setTimeout(() => { button.textContent = "Copy"; }, RESET_MS);
    });
    box.append(button);
  });
})();
