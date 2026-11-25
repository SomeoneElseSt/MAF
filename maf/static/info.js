// Small (i) buttons open an explanation card next to them (each has its own text, in an info-card
// right after it); clicking elsewhere or pressing Escape closes it.
let infoCard = null;

function cardFor(button) {
  return button.parentElement?.querySelector(":scope > .info-card") ?? null;
}

function placeCard(button) {
  // The card sits in a positioned parent right after its button: place it against that, in local
  // coordinates, and keep it inside the content column so it never widens the page.
  const box = button.getBoundingClientRect();
  const cardWidth = infoCard.offsetWidth;
  const column = document.querySelector(".page").getBoundingClientRect();
  const left = Math.min(box.left - 12, column.right - 20 - cardWidth);
  infoCard.style.left = `${Math.max(column.left + 20 - box.left, left - box.left)}px`;
  infoCard.style.top = `${button.offsetHeight + 8}px`;
}

function closeCard() {
  if (infoCard) infoCard.hidden = true;
  infoCard = null;
  document.querySelectorAll(".info[aria-expanded='true']").forEach(button => button.setAttribute("aria-expanded", "false"));
}

document.addEventListener("click", event => {
  const button = event.target.closest(".info");
  if (button) {
    event.preventDefault();
    const card = cardFor(button);
    if (!card) return;
    const opening = card.hidden || button.getAttribute("aria-expanded") !== "true";
    closeCard();
    if (!opening) return;
    infoCard = card;
    infoCard.hidden = false;
    placeCard(button);
    button.setAttribute("aria-expanded", "true");
    return;
  }
  if (infoCard && !infoCard.hidden && !event.target.closest(".info-card")) closeCard();
});

document.addEventListener("keydown", event => {
  if (event.key === "Escape") closeCard();
});
