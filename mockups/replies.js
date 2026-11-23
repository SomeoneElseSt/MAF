// Mockup-only: clicking Reply opens a reply box right under that comment, indented like a reply.
const MY_THREAD_ID = "calm-badger";

function buildReplyForm() {
  const form = document.createElement("form");
  form.className = "inline-reply";
  form.action = "item.html";
  form.innerHTML = `
    <textarea aria-label="Write a reply" placeholder="Write a reply"></textarea>
    <p class="help">Replying as: <button class="id" type="button">${MY_THREAD_ID}</button></p>
    <div class="row">
      <button class="button" type="submit">Reply</button>
      <button class="button plain cancel" type="button">Cancel</button>
    </div>`;
  form.querySelector(".cancel").addEventListener("click", () => form.remove());
  form.querySelector(".id").addEventListener("click", () => document.getElementById("id-dialog")?.showModal());
  return form;
}

document.querySelectorAll(".reply-toggle").forEach(button => {
  button.addEventListener("click", () => {
    const actions = button.closest(".actions");
    const alreadyOpen = actions.nextElementSibling?.classList.contains("inline-reply");
    document.querySelectorAll(".inline-reply").forEach(form => form.remove());
    if (alreadyOpen) return;
    const form = buildReplyForm();
    actions.after(form);
    form.querySelector("textarea").focus();
  });
});
