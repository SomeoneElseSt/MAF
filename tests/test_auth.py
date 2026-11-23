"""Sign-in: domain check, cooldown, code lifetime, blind signature and redeem.

Covers SPEC "Login flow" and the privacy rules. The browser half of the blind
signature is done in Python here (the same RFC 9474 steps), so the tests need no
Node; spike/blind proves the two implementations interoperate.
"""

import base64
import hashlib
import secrets

from maf import store
from maf.blind import PrivateKey, PublicKey, verify
from maf.util import sha256_hex

MODULUS_BITS = 2048


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


class Browser:
    """The client half of RFC 9474 RSABSSA-SHA384-PSS-Randomized, in Python."""

    def __init__(self, public_key: PublicKey) -> None:
        self._pk = public_key
        self.token = secrets.token_bytes(32)
        self.prepared = secrets.token_bytes(32) + self.token
        self._r = secrets.randbelow(public_key.n - 1) + 1
        while True:
            try:
                self.inv = pow(self._r, -1, public_key.n)
                break
            except ValueError:
                self._r = secrets.randbelow(public_key.n - 1) + 1
        from maf.blind import _mgf1

        self._mgf1 = _mgf1

    def blind(self) -> str:
        n = self._pk.n
        em_bits = n.bit_length() - 1
        em_len = (em_bits + 7) // 8
        m_hash = hashlib.sha384(self.prepared).digest()
        salt = secrets.token_bytes(48)
        h = hashlib.sha384(b"\x00" * 8 + m_hash + salt).digest()
        db = b"\x00" * (em_len - 48 - 48 - 2) + b"\x01" + salt
        masked = bytearray(a ^ b for a, b in zip(db, self._mgf1(h, em_len - 49)))
        masked[0] &= 0xFF >> (8 * em_len - em_bits)
        encoded = bytes(masked) + h + b"\xbc"
        blinded = (int.from_bytes(encoded, "big") * pow(self._r, self._pk.e, n)) % n
        self._encoded = encoded
        return b64(blinded.to_bytes(self._pk.modulus_len, "big"))

    def finalize(self, blind_sig_b64: str) -> bytes:
        blind_sig = int.from_bytes(unb64(blind_sig_b64), "big")
        signature = (blind_sig * self.inv) % self._pk.n
        sig = signature.to_bytes(self._pk.modulus_len, "big")
        assert verify(self._pk, sig, self.prepared), "browser-side PSS check failed"
        return sig

    def redeem_data(self, signature: bytes) -> dict:
        return {"token": b64(self.token), "prepared": b64(self.prepared), "signature": b64(signature)}


def latest_code(app) -> str:
    return next(iter(app.memory.codes.values()))[0]


def sign_in(client, app, email="student@uni.minerva.edu") -> dict:
    """Walks the whole flow and returns the redeem payload for reuse."""
    client.post("/login", data={"email": email})
    code = latest_code(app)
    browser = Browser(app.public_key)
    signed = client.post("/login/blind-sign", data={"email": email, "code": code, "blinded": browser.blind()})
    assert signed.status_code == 200, signed.text
    signature = browser.finalize(signed.json()["blind_sig"])
    return browser.redeem_data(signature)


# -- the domain gate -----------------------------------------------------


def test_other_domains_are_rejected(client, app):
    response = client.post("/login", data={"email": "someone@gmail.com"})
    assert response.status_code == 400
    assert app.memory.codes == {}


def test_minerva_email_is_accepted(client, app):
    response = client.post("/login", data={"email": "Student@UNI.Minerva.edu"}, follow_redirects=False)
    assert response.status_code == 303
    assert "student@uni.minerva.edu" in app.memory.codes


# -- cooldown and code lifetime -------------------------------------------


def test_cooldown_allows_one_code_per_ten_minutes(client, app):
    client.post("/login", data={"email": "student@uni.minerva.edu"})
    second = client.post("/login", data={"email": "student@uni.minerva.edu"})
    assert second.status_code == 429


def test_code_expires_after_ten_minutes(client, app, monkeypatch):
    client.post("/login", data={"email": "student@uni.minerva.edu"})
    code = latest_code(app)
    later = __import__("maf.memory", fromlist=["now"]).now() + 11 * 60
    monkeypatch.setattr("maf.memory.now", lambda: later)
    assert not app.memory.check_code("student@uni.minerva.edu", code)


def test_wrong_code_is_rejected_and_correct_one_is_consumed(client, app):
    client.post("/login", data={"email": "student@uni.minerva.edu"})
    code = latest_code(app)
    email = "student@uni.minerva.edu"
    assert not app.memory.check_code(email, "000000" if code != "000000" else "111111")
    assert app.memory.check_code(email, code)
    assert not app.memory.check_code(email, code)


def test_codes_are_six_digits(client, app):
    client.post("/login", data={"email": "student@uni.minerva.edu"})
    code = latest_code(app)
    assert len(code) == 6 and code.isdigit()


# -- blind signature -----------------------------------------------------


def test_blind_sign_requires_a_valid_code(client, app):
    browser = Browser(app.public_key)
    client.post("/login", data={"email": "student@uni.minerva.edu"})
    response = client.post("/login/blind-sign", data={"email": "student@uni.minerva.edu", "code": "000000", "blinded": browser.blind()})
    assert response.status_code == 400


def test_public_key_endpoint(client, app):
    key = client.get("/login/blind").json()
    assert key["hash"] == "SHA-384"
    assert key["saltLength"] == 48
    assert int(key["n"], 16) == app.public_key.n


# -- redeem --------------------------------------------------------------


def test_redeem_issues_a_pass(client, app):
    payload = sign_in(client, app)
    response = client.post("/redeem", data=payload, follow_redirects=False)
    assert response.status_code == 303
    assert "maf_pass" in client.cookies
    row = app.conn.execute("SELECT COUNT(*) AS n FROM pass").fetchone()
    assert row["n"] == 1


def test_a_token_cannot_be_redeemed_twice(client, app):
    payload = sign_in(client, app)
    assert client.post("/redeem", data=payload, follow_redirects=False).status_code == 303
    client.cookies.clear()
    again = client.post("/redeem", data=payload)
    assert again.status_code == 400


def test_redeem_rejects_a_forged_signature(client, app):
    payload = sign_in(client, app)
    payload["signature"] = b64(secrets.token_bytes(app.public_key.modulus_len))
    assert client.post("/redeem", data=payload).status_code == 400


def test_redeem_rejects_a_signature_for_another_message(client, app):
    payload = sign_in(client, app)
    other = Browser(app.public_key)
    client.post("/login", data={"email": "other@uni.minerva.edu"})
    signed = client.post("/login/blind-sign", data={"email": "other@uni.minerva.edu", "code": latest_code(app), "blinded": other.blind()})
    payload["signature"] = b64(other.finalize(signed.json()["blind_sig"]))
    assert client.post("/redeem", data=payload).status_code == 400


def test_redeem_rejects_a_token_not_matching_the_prepared_message(client, app):
    payload = sign_in(client, app)
    payload["token"] = b64(secrets.token_bytes(32))
    assert client.post("/redeem", data=payload).status_code == 400


def test_passes_have_no_created_at(app):
    columns = [r["name"] for r in app.conn.execute("PRAGMA table_info(pass)").fetchall()]
    assert columns == ["id"]
