// Verifies an RFC 9474 Appendix A signature with @cloudflare/blindrsa-ts,
// proving the JS library's verify agrees with the RFC's published values.
import { RSABSSA } from "@cloudflare/blindrsa-ts";
import { webcrypto } from "node:crypto";
import { readFileSync } from "node:fs";

const VECTORS = new URL("../vectors/", import.meta.url);
const vector = JSON.parse(readFileSync(new URL("RSABSSA-SHA384-PSS-Deterministic.json", VECTORS)));
const hex = s => Uint8Array.from(s.replace(/\s+/g, "").match(/../g).map(b => parseInt(b, 16)));
const b64url = h => Buffer.from(hex(h)).toString("base64url");

const publicKey = await webcrypto.subtle.importKey(
  "jwk",
  { kty: "RSA", n: b64url(vector.n), e: b64url(vector.e), ext: true, key_ops: ["verify"] },
  { name: "RSA-PSS", hash: "SHA-384" },
  true,
  ["verify"],
);
const suite = RSABSSA.SHA384.PSS.Deterministic();
const prepared = hex(vector.prepared_msg);
const ok = await suite.verify(publicKey, hex(vector.sig), prepared);
console.log(JSON.stringify({ variant: suite.toString(), rfcSignatureVerifies: ok }));
process.exit(ok ? 0 : 1);
