// JS half of the interop test, in three steps driven by run.sh:
//   blind   generates a key pair, blinds a fixed message (inv_A), saves blinded_A + inv_A
//   sign    BlindSigns Python's blinded_B, then Finalizes Python's signature of blinded_A
//   verify  checks that the signature finalized in `sign` verifies over the message
import { RSABSSA } from "@cloudflare/blindrsa-ts";
import { webcrypto } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";

const VECTORS = new URL("../vectors/", import.meta.url);
const STATE = new URL("interop.json", VECTORS);
const MESSAGE = new TextEncoder().encode("maf interop: python blind, js sign");
const suite = RSABSSA.SHA384.PSS.Randomized();
const read = () => JSON.parse(readFileSync(STATE));
const save = state => writeFileSync(STATE, JSON.stringify(state, null, 1) + "\n");
const hex = s => Uint8Array.from(s.match(/../g).map(b => parseInt(b, 16)));
const toHex = b => Buffer.from(b).toString("hex");

async function importKeys(state) {
  const publicKey = await webcrypto.subtle.importKey(
    "jwk", { ...state.key.public, ext: true, key_ops: ["verify"] },
    { name: "RSA-PSS", hash: "SHA-384" }, true, ["verify"]);
  const privateKey = await webcrypto.subtle.importKey(
    "jwk", { ...state.key.private, key_ops: ["sign"] },
    { name: "RSA-PSS", hash: "SHA-384" }, true, ["sign"]);
  return { publicKey, privateKey };
}

const steps = {
  // Direction A, step 1: JS blinds.
  async blind() {
    const { privateKey, publicKey } = await suite.generateKey({ modulusLength: 2048, publicExponent: Uint8Array.from([1, 0, 1]) });
    const key = {
      private: await webcrypto.subtle.exportKey("jwk", privateKey),
      public: await webcrypto.subtle.exportKey("jwk", publicKey),
    };
    const { blindedMsg, inv } = await suite.blind(publicKey, MESSAGE);
    save({ key, js_blinded_A: toHex(blindedMsg), js_inv_A: toHex(inv) });
    console.log("js blind done");
  },
  // Direction A, step 3 and direction B, step 2.
  async sign() {
    const state = read();
    const { publicKey, privateKey } = await importKeys(state);
    state.js_blind_sig_B = toHex(await suite.blindSign(privateKey, hex(state.py_blinded_B)));
    state.js_finalized_A = toHex(await suite.finalize(publicKey, MESSAGE, hex(state.py_blind_sig_A), hex(state.js_inv_A)));
    save(state);
    console.log("js blindSign (B) + finalize (A) done");
  },
  async verify() {
    const state = read();
    const { publicKey } = await importKeys(state);
    const ok = await suite.verify(publicKey, hex(state.js_finalized_A), MESSAGE);
    console.log("js finalized Python's blind signature of a JS blind and verified it:", ok);
    if (!ok) process.exit(1);
  },
};

const step = steps[process.argv[2]];
if (!step) {
  console.error("usage: node js/interop.mjs blind|sign|verify");
  process.exit(2);
}
await step();
