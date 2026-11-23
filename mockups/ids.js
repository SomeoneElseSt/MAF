// Opens the "no profiles" pop-up when any per-thread ID is clicked.
const idDialog = document.getElementById("id-dialog");

document.querySelectorAll(".anon-id").forEach(button => {
  button.addEventListener("click", () => idDialog.showModal());
});

idDialog?.querySelector("button")?.addEventListener("click", () => idDialog.close());
