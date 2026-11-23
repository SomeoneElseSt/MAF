"""Sign-in: domain check, cooldown, code lifetime, blind signature and redeem.

Covers SPEC "Login flow" and the privacy rules. The browser half of the blind
signature is done in Python here (the same RFC 9474 steps), so the tests need no
Node; spike/blind proves the two implementations interoperate.
"""

import base64
import hashlib
import secrets

from maf.blind import PublicKey, verify

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
    client.post("/sign-in", data={"email": email})
    code = latest_code(app)
    browser = Browser(app.public_key)
    signed = client.post("/sign-in/blind-sign", data={"email": email, "code": code, "blinded": browser.blind()})
    assert signed.status_code == 200, signed.text
    signature = browser.finalize(signed.json()["blind_sig"])
    return browser.redeem_data(signature)


# -- the domain gate -----------------------------------------------------


def test_other_domains_are_rejected(client, app):
    response = client.post("/sign-in", data={"email": "someone@gmail.com"})
    assert response.status_code == 400
    assert app.memory.codes == {}


def test_minerva_email_is_accepted(client, app):
    response = client.post("/sign-in", data={"email": "Student@UNI.Minerva.edu"}, follow_redirects=False)
    assert response.status_code == 200
    assert "student@uni.minerva.edu" in app.memory.codes


def test_code_form_carries_the_email_like_a_browser_would(client, app):
    """The browser only sends what the code form holds, so the form itself must carry the address."""
    page = client.post("/sign-in", data={"email": "student@uni.minerva.edu"}).text
    assert 'name="email" value="student@uni.minerva.edu"' in page
    assert "student@uni.minerva.edu" not in str(client.cookies)
    response = client.post("/sign-in/code", data={"email": "student@uni.minerva.edu", "code": latest_code(app)})
    assert response.status_code == 200


# -- cooldown and code lifetime -------------------------------------------


def test_cooldown_allows_one_code_per_thirty_seconds(client, app):
    client.post("/sign-in", data={"email": "student@uni.minerva.edu"})
    second = client.post("/sign-in", data={"email": "student@uni.minerva.edu"})
    assert second.status_code == 429
    import re

    seconds = int(re.search(r'data-wait="(\d+)"', second.text).group(1))
    assert 20 <= seconds <= 30
    assert f"Wait {seconds} seconds</button>" in second.text
    assert 'class="notice"' not in second.text


def test_code_expires_after_ten_minutes(client, app, monkeypatch):
    client.post("/sign-in", data={"email": "student@uni.minerva.edu"})
    code = latest_code(app)
    later = __import__("maf.memory", fromlist=["now"]).now() + 11 * 60
    monkeypatch.setattr("maf.memory.now", lambda: later)
    assert not app.memory.check_code("student@uni.minerva.edu", code)


def test_wrong_code_is_rejected_and_correct_one_is_consumed(client, app):
    client.post("/sign-in", data={"email": "student@uni.minerva.edu"})
    code = latest_code(app)
    email = "student@uni.minerva.edu"
    assert not app.memory.check_code(email, "000000" if code != "000000" else "111111")
    assert app.memory.check_code(email, code)
    assert not app.memory.check_code(email, code)


def test_codes_are_six_digits(client, app):
    client.post("/sign-in", data={"email": "student@uni.minerva.edu"})
    code = latest_code(app)
    assert len(code) == 6 and code.isdigit()


# -- blind signature -----------------------------------------------------


def test_blind_sign_requires_a_valid_code(client, app):
    browser = Browser(app.public_key)
    client.post("/sign-in", data={"email": "student@uni.minerva.edu"})
    response = client.post("/sign-in/blind-sign", data={"email": "student@uni.minerva.edu", "code": "000000", "blinded": browser.blind()})
    assert response.status_code == 400


def test_public_key_endpoint(client, app):
    key = client.get("/sign-in/key").json()
    assert key["hash"] == "SHA-384"
    assert key["saltLength"] == 48
    assert int(key["n"], 16) == app.public_key.n


# -- redeem --------------------------------------------------------------


def test_redeem_issues_a_pass(client, app):
    payload = sign_in(client, app)
    response = client.post("/sign-in/redeem", data=payload, follow_redirects=False)
    assert response.status_code == 303
    assert "maf_pass" in client.cookies
    row = app.conn.execute("SELECT COUNT(*) AS n FROM pass").fetchone()
    assert row["n"] == 1


def test_a_token_cannot_be_redeemed_twice(client, app):
    payload = sign_in(client, app)
    assert client.post("/sign-in/redeem", data=payload, follow_redirects=False).status_code == 303
    client.cookies.clear()
    again = client.post("/sign-in/redeem", data=payload)
    assert again.status_code == 400


def test_redeem_rejects_a_forged_signature(client, app):
    payload = sign_in(client, app)
    payload["signature"] = b64(secrets.token_bytes(app.public_key.modulus_len))
    assert client.post("/sign-in/redeem", data=payload).status_code == 400


def test_redeem_rejects_a_signature_for_another_message(client, app):
    payload = sign_in(client, app)
    other = Browser(app.public_key)
    client.post("/sign-in", data={"email": "other@uni.minerva.edu"})
    signed = client.post("/sign-in/blind-sign", data={"email": "other@uni.minerva.edu", "code": latest_code(app), "blinded": other.blind()})
    payload["signature"] = b64(other.finalize(signed.json()["blind_sig"]))
    assert client.post("/sign-in/redeem", data=payload).status_code == 400


def test_redeem_rejects_a_token_not_matching_the_prepared_message(client, app):
    payload = sign_in(client, app)
    payload["token"] = b64(secrets.token_bytes(32))
    assert client.post("/sign-in/redeem", data=payload).status_code == 400


def test_passes_have_no_created_at(app):
    columns = [r["name"] for r in app.conn.execute("PRAGMA table_info(pass)").fetchall()]
    assert columns == ["id"]


def test_code_page_then_blind_sign_works_like_a_browser(client, app):
    """The code page checks the code without using it up, so the blind-sign step right after still accepts it."""
    client.post("/sign-in", data={"email": "student@uni.minerva.edu"})
    code = latest_code(app)
    assert client.post("/sign-in/code", data={"email": "student@uni.minerva.edu", "code": code}).status_code == 200
    browser = Browser(app.public_key)
    signed = client.post("/sign-in/blind-sign", data={"email": "student@uni.minerva.edu", "code": code, "blinded": browser.blind()})
    assert signed.status_code == 200
    assert signed.json().get("blind_sig")


def test_five_wrong_codes_make_continue_wait_30_seconds(client, app):
    from maf import memory as memory_module

    client.post("/sign-in", data={"email": "student@uni.minerva.edu"})
    code = latest_code(app)
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(4):
        page = client.post("/sign-in/code", data={"email": "student@uni.minerva.edu", "code": wrong})
        assert "data-wait" not in page.text
    fifth = client.post("/sign-in/code", data={"email": "student@uni.minerva.edu", "code": wrong})
    assert "That code didn&#39;t match" in fifth.text
    assert 'data-wait="30" data-label="Continue">Wait 30 seconds</button>' in fifth.text
    # Even the right code waits, or the wait would only slow guessing down by one request.
    waiting = client.post("/sign-in/code", data={"email": "student@uni.minerva.edu", "code": code})
    assert waiting.status_code == 429 and "That code didn&#39;t match" not in waiting.text
    assert "data-wait=" in waiting.text
    app.memory.code_locks["student@uni.minerva.edu"] = memory_module.now() - 1  # 30 seconds later
    later = client.post("/sign-in/code", data={"email": "student@uni.minerva.edu", "code": code})
    assert later.status_code == 200 and "Signing you in" in later.text


def test_code_page_offers_a_new_code_once_the_cooldown_runs_out(client, app):
    import re

    page = client.post("/sign-in", data={"email": "student@uni.minerva.edu"}).text
    seconds = int(re.search(r'class="note resend"[^>]*data-seconds="(\d+)"', page).group(1))
    assert 20 <= seconds <= 30
    assert ">Send a new code</button>" in page and "disabled" not in page
    assert 'id="resend-form" action="/sign-in"' in page


def test_empty_fields_get_the_sites_own_message_not_the_browsers(client, app):
    for page in (client.get("/sign-in").text, client.post("/sign-in", data={"email": "student@uni.minerva.edu"}).text):
        assert "novalidate" in page and " required" not in page
    empty_email = client.post("/sign-in", data={"email": ""})
    assert empty_email.status_code == 400 and "Please enter a valid email." in empty_email.text
    empty_code = client.post("/sign-in/code", data={"email": "student@uni.minerva.edu", "code": ""})
    assert empty_code.status_code == 400 and "Enter the 6-digit code from the email." in empty_code.text


def test_sign_in_pages_say_already_signed_in(signed_in):
    pages = [("GET", "/sign-in"), ("POST", "/sign-in"), ("GET", "/sign-in/code"), ("POST", "/sign-in/code"), ("GET", "/sign-in/redeem")]
    for method, path in pages:
        response = signed_in.request(method, path, data={"email": "student@uni.minerva.edu", "code": "123456"})
        assert response.status_code == 200, path
        assert "already signed in" in response.text, path
        assert '<a href="/">home</a>' in response.text, path


def test_dev_login_code_only_works_locally():
    from maf.settings import DEV_LOGIN_CODE, load_settings

    assert DEV_LOGIN_CODE == "139145"
    local = load_settings({"EMAIL_BACKEND": "console", "MAF_ENV": "development"})
    assert local.dev_login_code == DEV_LOGIN_CODE
    assert load_settings({"EMAIL_BACKEND": "ses", "MAF_ENV": "development"}).dev_login_code is None


def test_dev_login_code_can_never_be_on_in_production():
    import pytest

    from maf.settings import ConfigError, load_settings

    with pytest.raises(ConfigError):
        load_settings({"EMAIL_BACKEND": "console", "MAF_ENV": "production"})


def test_production_refuses_the_public_dev_secrets():
    import pytest

    from maf.settings import ConfigError, load_settings

    with pytest.raises(ConfigError):
        load_settings({"MAF_ENV": "production", "EMAIL_BACKEND": "ses"})


def test_only_plain_minerva_addresses_are_accepted():
    from maf.auth import normalise_email

    assert normalise_email("  Jane.Doe+x@UNI.minerva.edu ") == "jane.doe+x@uni.minerva.edu"
    for sneaky in ["attacker@gmail.com,victim@uni.minerva.edu", "x <attacker@gmail.com>, y@uni.minerva.edu",
                   "a@b@uni.minerva.edu", '"a b"@uni.minerva.edu', "a@uni.minerva.edu.evil.com",
                   "a@xuni.minerva.edu", "a b@uni.minerva.edu", "a@uni.minerva.edu\nbcc:x@gmail.com"]:
        assert normalise_email(sneaky) is None, sneaky


def test_wrong_codes_are_capped_site_wide():
    from maf.memory import SITE_WRONG_CODES_LIMIT, Memory

    memory = Memory()
    emails = [f"s{i}@uni.minerva.edu" for i in range(SITE_WRONG_CODES_LIMIT + 1)]
    codes = {email: memory.issue_code(email) for email in emails}
    for email in emails[:SITE_WRONG_CODES_LIMIT]:
        wrong = f"{(int(codes[email]) + 1) % 1_000_000:06d}"
        assert not memory.check_code(email, wrong)
    assert memory.code_guessing_paused()
    last = emails[-1]
    assert not memory.check_code(last, codes[last])  # even the right code waits, or guessing could continue


def test_code_page_says_when_guessing_is_paused(client, app):
    from maf.memory import SITE_WRONG_CODES_LIMIT, now

    app.memory.wrong_codes = [now()] * SITE_WRONG_CODES_LIMIT
    response = client.post("/sign-in/code", data={"email": "s@uni.minerva.edu", "code": "123456"})
    assert response.status_code == 429
    assert "MAF is currently under maintenance. Try again in 60 minutes." in response.text


def test_maintainer_gets_one_email_when_sign_ins_pause(client, app, capsys):
    from maf.memory import SITE_WRONG_CODES_LIMIT, now

    app.memory.wrong_codes = [now()] * (SITE_WRONG_CODES_LIMIT - 1)
    client.post("/sign-in", data={"email": "s@uni.minerva.edu"})
    capsys.readouterr()
    client.post("/sign-in/code", data={"email": "s@uni.minerva.edu", "code": "000001"})
    client.post("/sign-in/code", data={"email": "s@uni.minerva.edu", "code": "000002"})
    client.post("/sign-in/blind-sign", data={"email": "s@uni.minerva.edu", "code": "000003", "blinded": "x"})
    out = capsys.readouterr().out
    assert out.count("[email to maintainer@example.com] Sign-ins paused: 30 wrong codes in the last hour") == 1


def test_paused_email_layout():
    from datetime import UTC, datetime

    from maf.email import sign_in_paused_email

    email = sign_in_paused_email("hello@maforum.net", 45, now=datetime(2026, 11, 23, 22, 0, tzinfo=UTC))
    assert email.body == "Sign-ins paused: 30 wrong codes in the last hour\nResumes by 22:45 UTC, as of 23/11/26 22:00 UTC\n"
    assert ">MAF</p>" in email.html
