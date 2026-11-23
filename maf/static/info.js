// Small (i) buttons open a shared explanation card next to them; clicking elsewhere or pressing Escape closes it.
const infoCard = document.getElementById("private-info");

function placeCard(button) {
  const box = button.getBoundingClientRect();
  const cardWidth = infoCard.offsetWidth;
  // Keep the card inside the content column so it never sticks out past the page margins.
  const column = document.querySelector(".page").getBoundingClientRect();
  const columnLeft = column.left + window.scrollX + 20;
  const columnRight = column.right + window.scrollX - 20;
  const left = Math.min(box.left + window.scrollX - 12, columnRight - cardWidth);
  infoCard.style.left = `${Math.max(columnLeft, left)}px`;
  infoCard.style.top = `${box.bottom + window.scrollY + 8}px`;
}

function closeCard() {
  infoCard.hidden = true;
  document.querySelectorAll(".info[aria-expanded='true']").forEach(button => button.setAttribute("aria-expanded", "false"));
}

document.addEventListener("click", event => {
  const button = event.target.closest(".info");
  if (button) {
    event.preventDefault();
    const opening = infoCard.hidden || button.getAttribute("aria-expanded") !== "true";
    closeCard();
    if (!opening) return;
    infoCard.hidden = false;
    placeCard(button);
    button.setAttribute("aria-expanded", "true");
    return;
  }
  if (!infoCard.hidden && !event.target.closest("#private-info")) closeCard();
});

document.addEventListener("keydown", event => {
  if (event.key === "Escape") closeCard();
});
