// Opens the "IDs change per thread" pop-up when any per-thread ID is clicked.
const idDialog = document.getElementById("id-dialog");

document.querySelectorAll(".id").forEach(button => {
  button.addEventListener("click", () => idDialog.showModal());
});

idDialog?.querySelector("button")?.addEventListener("click", () => idDialog.close());
