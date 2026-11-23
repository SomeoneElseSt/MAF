// Login blind-signature step. After the code is accepted, this blinds a random
// token, sends only the blinded value, unblinds the signature and redeems it.
// The token never leaves the browser unblinded until /redeem.
(function () {
  const form = document.querySelector("form[data-blind]");
  if (!form || !window.BlindRSA) return;

  const TOKEN_BYTES = 32;
  const suite = window.BlindRSA.SHA384.PSS.Randomized();
  const status = form.querySelector(".blind-status");
  const submit = form.querySelector("button[type=submit]");

  function base64url(bytes) {
    return btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }

  function fromBase64url(value) {
    const padded = value.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (value.length % 4)) % 4);
    return Uint8Array.from(atob(padded), c => c.charCodeAt(0));
  }

  async function publicKey() {
    const response = await fetch("/login/blind", { headers: { accept: "application/json" } });
    const { n, e } = await response.json();
    const toB64 = hex => base64url(Uint8Array.from(hex.match(/../g).map(b => parseInt(b, 16))));
    return crypto.subtle.importKey(
      "jwk",
      { kty: "RSA", n: toB64(n), e: toB64(e), ext: true, key_ops: ["verify"] },
      { name: "RSA-PSS", hash: "SHA-384" },
      true,
      ["verify"],
    );
  }

  form.addEventListener("submit", async event => {
    event.preventDefault();
    submit.disabled = true;
    try {
      const key = await publicKey();
      const token = crypto.getRandomValues(new Uint8Array(TOKEN_BYTES));
      const prepared = suite.prepare(token);
      const { blindedMsg, inv } = await suite.blind(key, prepared);
      const body = new FormData(form);
      body.set("blinded", base64url(blindedMsg));
      const signed = await fetch("/login/blind-sign", { method: "POST", body });
      const { blind_sig: blindSig } = await signed.json();
      if (!blindSig) throw new Error("not signed");
      const signature = await suite.finalize(key, prepared, fromBase64url(blindSig), inv);
      const redeem = new FormData();
      redeem.set("token", base64url(token));
      redeem.set("prepared", base64url(prepared));
      redeem.set("signature", base64url(signature));
      const redeemed = await fetch("/redeem", { method: "POST", body: redeem, redirect: "follow" });
      window.location.assign(redeemed.ok ? "/" : "/redeem");
    } catch {
      status.textContent = "Something went wrong. Try again, or sign in again.";
      submit.disabled = false;
    }
  });
})();
