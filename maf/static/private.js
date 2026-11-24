// Private replies are encrypted here, in the browser, so MAF's server only ever stores scrambled text.
// Each person has a separate key pair for each thread they write in, kept in this browser (IndexedDB).
// Only the public half goes to the server; per-thread keys can't link someone's threads together.
// Both people derive the same secret (ECDH P-256 between their keys, then HKDF) and use it with AES-GCM.
(function () {
  const root = document.querySelector("[data-thread]");
  if (!root || !window.crypto || !crypto.subtle || !window.indexedDB) return;

  const threadId = root.dataset.thread;
  const encoder = new TextEncoder();
  const CURVE = { name: "ECDH", namedCurve: "P-256" };
  const SEALED_VERSION = 1;
  const IV_BYTES = 12;

  function base64url(bytes) {
    return btoa(String.fromCharCode(...new Uint8Array(bytes))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }

  function fromBase64url(value) {
    const padded = value.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (value.length % 4)) % 4);
    return Uint8Array.from(atob(padded), c => c.charCodeAt(0));
  }

  function keyStore(mode, action) {
    return new Promise((resolve, reject) => {
      const opening = indexedDB.open("maf", 1);
      opening.onupgradeneeded = () => opening.result.createObjectStore("thread-keys");
      opening.onerror = () => reject(opening.error);
      opening.onsuccess = () => {
        const request = action(opening.result.transaction("thread-keys", mode).objectStore("thread-keys"));
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
      };
    });
  }

  const loadPair = () => keyStore("readonly", store => store.get(threadId));

  // The private key is created non-extractable: scripts can use it but never read it out.
  async function ownPair() {
    const saved = await loadPair();
    if (saved) return saved;
    const pair = await crypto.subtle.generateKey(CURVE, false, ["deriveBits"]);
    const fresh = { privateKey: pair.privateKey, publicKey: base64url(await crypto.subtle.exportKey("raw", pair.publicKey)) };
    await keyStore("readwrite", store => store.put(fresh, threadId));
    return fresh;
  }

  async function sharedKey(privateKey, otherPublicKey) {
    const other = await crypto.subtle.importKey("raw", fromBase64url(otherPublicKey), CURVE, false, []);
    const secret = await crypto.subtle.deriveBits({ name: "ECDH", public: other }, privateKey, 256);
    const material = await crypto.subtle.importKey("raw", secret, "HKDF", false, ["deriveKey"]);
    return crypto.subtle.deriveKey(
      { name: "HKDF", hash: "SHA-256", salt: encoder.encode(threadId), info: encoder.encode("maf private reply v1") },
      material,
      { name: "AES-GCM", length: 256 },
      false,
      ["encrypt", "decrypt"],
    );
  }

  async function seal(text, pair, peerKey) {
    const iv = crypto.getRandomValues(new Uint8Array(IV_BYTES));
    const key = await sharedKey(pair.privateKey, peerKey);
    const cipher = await crypto.subtle.encrypt({ name: "AES-GCM", iv, additionalData: encoder.encode(threadId) }, key, encoder.encode(text));
    return JSON.stringify({ v: SEALED_VERSION, iv: base64url(iv), ct: base64url(cipher), from: pair.publicKey, to: peerKey });
  }

  async function unseal(raw, pair) {
    const sealed = JSON.parse(raw);
    if (sealed.from !== pair.publicKey && sealed.to !== pair.publicKey) throw new Error("not for this key");
    const other = sealed.from === pair.publicKey ? sealed.to : sealed.from;
    const key = await sharedKey(pair.privateKey, other);
    const plain = await crypto.subtle.decrypt(
      { name: "AES-GCM", iv: fromBase64url(sealed.iv), additionalData: encoder.encode(threadId) }, key, fromBase64url(sealed.ct));
    return new TextDecoder().decode(plain);
  }

  // People who've written in this thread publish their public key, so others can reply to them privately.
  async function registerKey() {
    if (!root.hasAttribute("data-my-key")) return;
    const pair = await ownPair();
    if (pair.publicKey === root.dataset.myKey) return;
    const body = new FormData();
    body.set("thread_id", threadId);
    body.set("public_key", pair.publicKey);
    await fetch("/thread-key", { method: "POST", body });
  }

  async function openSealed() {
    const sealedItems = document.querySelectorAll("[data-sealed]");
    if (!sealedItems.length) return;
    const pair = await loadPair();
    if (!pair) return;
    for (const item of sealedItems) {
      try {
        item.textContent = await unseal(item.dataset.sealed, pair);
        item.classList.add("open");
      } catch {
        // Sealed for a key this browser doesn't have: the "only on the device" text stays.
      }
    }
  }

  function showError(form, message) {
    let note = form.querySelector(".private-error");
    if (!note) {
      note = document.createElement("p");
      note.className = "help private-error";
      note.setAttribute("role", "alert");
      form.querySelector(".row")?.before(note);
    }
    note.textContent = message;
  }

  function setUpForm(form) {
    const toggle = form.querySelector(".private-toggle");
    const checkbox = toggle?.querySelector("input[type='checkbox']");
    const peerKey = form.dataset.peerKey;
    if (!toggle || !checkbox || !peerKey) return;
    toggle.hidden = false;
    // Coming back with Back after a private send: give the box its name again for the next reply.
    window.addEventListener("pageshow", () => form.querySelector("textarea")?.setAttribute("name", "text"));
    form.addEventListener("submit", async event => {
      if (!checkbox.checked) return;
      event.preventDefault();
      const textarea = form.querySelector("textarea");
      if (!textarea.value.trim()) {
        textarea.focus();
        return;
      }
      try {
        const sealed = await seal(textarea.value.trim(), await ownPair(), peerKey);
        let field = form.querySelector("input[name='sealed']");
        if (!field) {
          field = document.createElement("input");
          field.type = "hidden";
          field.name = "sealed";
          form.append(field);
        }
        field.value = sealed;
        // The words themselves never leave the browser: only the sealed copy is sent.
        textarea.removeAttribute("name");
        form.submit();
      } catch {
        showError(form, "Couldn't encrypt this reply in this browser, so it wasn't sent.");
      }
    });
  }

  document.querySelectorAll("form[data-peer-key]").forEach(setUpForm);
  registerKey().catch(() => {});
  openSealed().catch(() => {});
})();
