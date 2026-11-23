// Mockup-only: clicking Reply opens a reply box right under that comment, indented like a reply.
const MY_THREAD_ID = "calm-badger";

// Replies inside a private exchange stay private, so the toggle comes on and locked.
function buildReplyForm(recipient, insidePrivate) {
  const form = document.createElement("form");
  form.className = "inline-reply";
  form.action = "item.html";
  form.innerHTML = `
    <textarea aria-label="Write a reply" placeholder="Write a reply"></textarea>
    <p class="help">Replying as: <button class="id" type="button">${MY_THREAD_ID}</button> <span class="dot">·</span> <span class="private-toggle"><label>Make only visible to ${recipient} <input type="checkbox"${insidePrivate ? " checked disabled" : ""}></label><button class="info" type="button" aria-label="About private replies" aria-expanded="false">i</button></span></p>
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
    const comment = button.closest(".comment");
    const recipient = comment.querySelector(".meta .id").textContent;
    const form = buildReplyForm(recipient, comment.classList.contains("private"));
    actions.after(form);
    form.querySelector("textarea").focus();
  });
});
