# Plan 004: Make the ElevenLabs webhook fail closed and lock down the unauthenticated ElevenLabs endpoints

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat abdd987..HEAD -- huf/ai/providers/elevenlabs_convai_api.py`
> If that file changed since this plan was written, compare the "Current state"
> excerpts against the live code before proceeding; on a mismatch, treat it as a
> STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: MED
- **Depends on**: none (creates/uses `huf/ai/tests/` — if absent, create `huf/ai/tests/__init__.py`)
- **Category**: security
- **Planned at**: commit `abdd987`, 2026-06-13

## Why this matters

`huf/ai/providers/elevenlabs_convai_api.py` exposes four `@frappe.whitelist(allow_guest=True)` endpoints — all callable by anonymous internet users. Two concrete problems, confirmed by reading the code:

1. **Webhook auth is fail-OPEN (SEC-01).** `handle_elevenlabs_webhook` wraps its entire HMAC signature check in `if sig_header:`. A request that simply omits the `elevenlabs-signature` header skips verification and proceeds to insert `Agent Run`/`Agent Message` rows (`ignore_permissions=True`) and trigger a server-side authenticated GET to the ElevenLabs audio API using the owner's stored API key. An unauthenticated caller can forge call records and make the owner pay for outbound API calls. The constant-time compare (`hmac.compare_digest`) inside the block is fine — the bug is purely the fail-open guard.

2. **Credential metadata + paid-API abuse (SEC-03).** `health()` returns `apiKeyLength`/`agentIdLength` to anonymous callers (a credential-length oracle). `get_signed_url()` performs an authenticated call with the owner's API key and returns a usable signed conversation URL to anyone, with no auth/rate limit — draining the owner's paid ElevenLabs quota. `get_agent_id()` leaks the configured agent id to anonymous callers.

The React frontend (`frontend/src`) does **not** call any of these endpoints (verified: zero matches for `get_signed_url`/`get_agent_id`/`convai`/`elevenlabs` under `frontend/src`), so they are consumed only by an external embedded voice widget or are unused. This plan makes the webhook fail closed (always), removes the credential-length leak from `health` (always), and gates the `allow_guest` removal on `get_signed_url`/`get_agent_id` behind an operator decision because an external embed may legitimately need them.

## Current state

File: `huf/ai/providers/elevenlabs_convai_api.py` (231 lines). Imports already present at top: `frappe`, `requests`, `hmac`, `hashlib`, `time`, `datetime`/`timedelta`, `ConversationManager`, `save_file`.

Verified excerpt — `huf/ai/providers/elevenlabs_convai_api.py:29-41` (the credential-length leak in `health`):

```python
@frappe.whitelist(allow_guest=True)
def health():
    agent_id, api_key = _get_settings()

    return {
        "status": "ok",
        "settings": {
            "hasAgentId": bool(agent_id),
            "hasApiKey": bool(api_key),
            "agentIdLength": len(agent_id) if agent_id else 0,
            "apiKeyLength": len(api_key) if api_key else 0,
        },
    }
```

Verified excerpt — `huf/ai/providers/elevenlabs_convai_api.py:87-130` (the fail-open webhook auth):

```python
@frappe.whitelist(allow_guest=True)
def handle_elevenlabs_webhook(type=None, data=None, event_timestamp=None):
    """
    Handles ElevenLabs Post Call Transcription.
    Validates against 'Elevenlabs Settings' and finds the linked Huf Agent.
    """
    request = frappe.request

    el_settings = frappe.get_single("Elevenlabs Settings")

    secret = el_settings.get_password("webhook_secret")
    provider = frappe.get_doc("AI Provider", el_settings.provider)
    api_key = provider.get_password("api_key")
    stored_agent_id = el_settings.agent_id

    if not secret:
        frappe.log_error("Webhook Secret missing in Elevenlabs Settings", "Huf Webhook")
        return {"status": "error", "message": "Configuration error"}

    sig_header = request.headers.get("elevenlabs-signature")
    if sig_header:
        try:
            parts = sig_header.split(",")
            t_part = parts[0].split("=")[1]
            v0_part = parts[1].split("=")[1]

            if int(time.time()) - int(t_part) > 300:
                frappe.throw("Timestamp expired", exc=frappe.PermissionError)

            raw_body = request.get_data()
            payload_to_sign = f"{t_part}.".encode("utf-8") + raw_body

            calculated = hmac.new(
                key=secret.encode("utf-8"),
                msg=payload_to_sign,
                digestmod=hashlib.sha256,
            ).hexdigest()

            if not hmac.compare_digest(v0_part, calculated):
                frappe.throw("Invalid Signature", exc=frappe.PermissionError)
        except Exception as e:
            frappe.log_error(f"Signature Failed: {str(e)}", "ElevenLabs Security")
            return {"status": "forbidden"}

    if type != "post_call_transcription" or not data:
        return {"status": "ignored"}
```

The bug: when `sig_header` is falsy (header omitted), the whole `if sig_header:` block is skipped and execution falls straight to the `if type != ...` line and onward into record creation. There is no `else` that rejects the unsigned request.

Verified excerpt — `huf/ai/providers/elevenlabs_convai_api.py:44-84` (`get_signed_url` and `get_agent_id`, both guest):

```python
@frappe.whitelist(allow_guest=True)
def get_signed_url():
    agent_id, api_key = _get_settings()
    ...
    response = requests.get(url, headers=headers, timeout=30)
    ...
    return {"signedUrl": data.get("signed_url")}


@frappe.whitelist(allow_guest=True)
def get_agent_id():
    agent_id, _ = _get_settings()
    return {"agentId": agent_id}
```

Repo conventions: raises use `frappe.throw(_("msg"), frappe.SomeError)` but this file uses bare `frappe.throw("msg", exc=...)` and returns dicts for webhook responses. Tests subclass `FrappeTestCase` from `frappe.tests.utils` (see `huf/ai/tests/test_flow_eval.py` once plan 001 has run, or `huf/huf/doctype/agent_chat/test_agent_chat.py`). Test files are tab-indented, double quotes, line length ≤ 110.

## Commands you will need

| Purpose             | Command                                                                                   | Expected on success |
|---------------------|-------------------------------------------------------------------------------------------|---------------------|
| Run elevenlabs test | `bench --site <sitename> run-tests --app huf --module huf.ai.tests.test_elevenlabs_convai` | `OK`                |
| All app tests       | `bench --site <sitename> run-tests --app huf`                                              | `OK`                |
| Confirm helper      | `grep -n "_verify_webhook_signature" huf/ai/providers/elevenlabs_convai_api.py`           | ≥2 matches (def + call) |
| Confirm leak gone   | `grep -n "apiKeyLength\|agentIdLength" huf/ai/providers/elevenlabs_convai_api.py`          | no matches          |
| Frontend callers    | `grep -rni "get_signed_url\|get_agent_id\|convai\|elevenlabs" frontend/src`                | no matches (expected) |

Replace `<sitename>` with the bench site. If you cannot determine it, that is a STOP condition — do not invent one.

## Scope

**In scope** (the only files you should modify):
- `huf/ai/providers/elevenlabs_convai_api.py` — extract `_verify_webhook_signature`, make the webhook fail closed, remove credential-length fields from `health`, and (decision-gated, Step 3) tighten `get_signed_url`/`get_agent_id`.
- `huf/ai/tests/test_elevenlabs_convai.py` (create). Create `huf/ai/tests/__init__.py` if plan 001 has not run and it does not exist.
- `plans/README.md` — status row update.

**Out of scope** (do NOT touch):
- The record-creation logic (lines 131-230: `ConversationManager`, `Agent Run` insert, audio download, transcript loop). The fix is the auth gate, not the body.
- `_get_settings()` — leave as is.
- `handle_elevenlabs_webhook`'s `allow_guest=True` decorator — external webhooks legitimately need guest access; the fix is mandatory signature verification, NOT removing guest access. KEEP the decorator.
- SSRF / `http_handler.py` (plan 002), `flow_api.py` (plan 003).

## Git workflow

- Branch: `advisor/004-elevenlabs-guest-endpoints`
- Commit per logical unit: (1) webhook fail-closed + helper, (2) health leak removal, (3) decision-gated guest tightening, (4) tests. Or fewer if cleaner. Message style: conventional commits (`fix:`). Suggested: `fix: require ElevenLabs webhook signature and lock down guest endpoints`.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Extract a pure signature helper and make the webhook fail closed (SEC-01)

In `huf/ai/providers/elevenlabs_convai_api.py`:

1. Add a module-level pure helper above `handle_elevenlabs_webhook`. Target shape (4-space indent — this file uses spaces, not tabs; match the existing file):

```python
def _verify_webhook_signature(secret, sig_header, raw_body):
    """Return True only if sig_header carries a valid, unexpired HMAC for raw_body.

    Fails closed: returns False if the secret is unset, the header is missing or
    malformed, the timestamp is outside the 5-minute window, or the signature
    does not match. Never raises.
    """
    if not secret or not sig_header:
        return False
    try:
        parts = sig_header.split(",")
        t_part = parts[0].split("=")[1]
        v0_part = parts[1].split("=")[1]
    except (IndexError, AttributeError):
        return False
    try:
        if int(time.time()) - int(t_part) > 300:
            return False
    except (ValueError, TypeError):
        return False
    payload_to_sign = f"{t_part}.".encode("utf-8") + raw_body
    calculated = hmac.new(
        key=secret.encode("utf-8"),
        msg=payload_to_sign,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(v0_part, calculated)
```

2. Replace the entire `sig_header = request.headers.get(...)` + `if sig_header:` block (current lines 106-129) with a fail-closed gate:

```python
    raw_body = request.get_data()
    sig_header = request.headers.get("elevenlabs-signature")
    if not _verify_webhook_signature(secret, sig_header, raw_body):
        frappe.log_error("ElevenLabs webhook signature verification failed", "ElevenLabs Security")
        return {"status": "forbidden"}
```

The existing `if not secret:` block (lines 102-104) stays — it already fails closed on a missing secret. After this change, ANY request without a valid signature returns `{"status": "forbidden"}` before any record is created. Do NOT log `secret`, `api_key`, or the raw signature value.

**Verify**: `grep -n "if sig_header:" huf/ai/providers/elevenlabs_convai_api.py` → no matches (fail-open guard removed).
**Verify**: `grep -n "_verify_webhook_signature" huf/ai/providers/elevenlabs_convai_api.py` → def + one call.

### Step 2: Remove the credential-length leak from `health` (SEC-03, unconditional)

In `health()`, delete the `agentIdLength` and `apiKeyLength` keys. Keep `hasAgentId`/`hasApiKey` booleans (presence flags are acceptable for a health check; exact lengths are an oracle). Resulting return:

```python
    return {
        "status": "ok",
        "settings": {
            "hasAgentId": bool(agent_id),
            "hasApiKey": bool(api_key),
        },
    }
```

**Verify**: `grep -n "apiKeyLength\|agentIdLength" huf/ai/providers/elevenlabs_convai_api.py` → no matches.

### Step 3 (DECISION GATE): Tighten `get_signed_url` and `get_agent_id`

These two endpoints are guest-callable and the React app does not use them. Before changing their access, determine the intended caller:

1. Run `grep -rni "get_signed_url\|get_agent_id\|convai\|elevenlabs" frontend/src` → expected: no matches (confirms the React app is not the caller).
2. Ask the operator: "Is there an external embedded ElevenLabs voice widget (outside this React app) that calls `get_signed_url` / `get_agent_id` without an authenticated Frappe session?"

- **If the operator says NO external public caller needs them** (or you can confirm only authenticated UI uses them): remove `allow_guest=True` from BOTH `get_signed_url` and `get_agent_id` (change `@frappe.whitelist(allow_guest=True)` to `@frappe.whitelist()`). This forces an authenticated session.
- **If the operator says YES, a public embed needs `get_signed_url`**: do NOT remove guest access from `get_signed_url`. Instead add Frappe rate limiting to it and leave `get_agent_id` as guest only if also required. Add the decorator `@frappe.rate_limiter(limit=10, seconds=60)` above `@frappe.whitelist(allow_guest=True)` (confirm `frappe.rate_limiter` exists in this Frappe version with `grep -rn "rate_limiter" $(bench --site <sitename> find-app-path frappe 2>/dev/null || echo ../frappe)` or via the Frappe docs; if it does not exist, leave guest access but report that rate limiting could not be added).
- **If you cannot reach the operator and cannot confirm the caller**: STOP and report (see STOP conditions). Do NOT guess — removing guest access could break a live voice widget, and leaving it wastes the hardening.

Whatever you choose, record the decision in your final report.

**Verify**: `grep -n "allow_guest=True" huf/ai/providers/elevenlabs_convai_api.py` → `handle_elevenlabs_webhook` MUST still have it; `health`/`get_signed_url`/`get_agent_id` per the decision above.

### Step 4: Write `huf/ai/tests/test_elevenlabs_convai.py`

If `huf/ai/tests/__init__.py` does not exist, create it empty first.

Unit-test the pure helper `_verify_webhook_signature` (no DB, deterministic). Target shape:

```python
import hashlib
import hmac
import time

import frappe
from frappe.tests.utils import FrappeTestCase

from huf.ai.providers.elevenlabs_convai_api import _verify_webhook_signature


def _sign(secret, body, t=None):
    t = t if t is not None else int(time.time())
    calculated = hmac.new(secret.encode("utf-8"), f"{t}.".encode("utf-8") + body, hashlib.sha256).hexdigest()
    return f"t={t},v0={calculated}"


class TestWebhookSignature(FrappeTestCase):
    def test_valid_signature_accepted(self):
        secret, body = "shh", b'{"type":"x"}'
        self.assertTrue(_verify_webhook_signature(secret, _sign(secret, body), body))

    def test_missing_header_rejected(self):
        # The core SEC-01 fix: no header -> fail closed.
        self.assertFalse(_verify_webhook_signature("shh", None, b"{}"))

    def test_empty_header_rejected(self):
        self.assertFalse(_verify_webhook_signature("shh", "", b"{}"))

    def test_missing_secret_rejected(self):
        self.assertFalse(_verify_webhook_signature("", _sign("shh", b"{}"), b"{}"))

    def test_wrong_signature_rejected(self):
        body = b'{"type":"x"}'
        self.assertFalse(_verify_webhook_signature("shh", _sign("shh", b"different"), body))

    def test_tampered_body_rejected(self):
        secret = "shh"
        sig = _sign(secret, b'{"amount":1}')
        self.assertFalse(_verify_webhook_signature(secret, sig, b'{"amount":9999}'))

    def test_expired_timestamp_rejected(self):
        secret, body = "shh", b"{}"
        old = int(time.time()) - 600  # 10 min ago, outside the 5-min window
        self.assertFalse(_verify_webhook_signature(secret, _sign(secret, body, t=old), body))

    def test_malformed_header_rejected(self):
        self.assertFalse(_verify_webhook_signature("shh", "garbage-no-commas", b"{}"))
```

**Verify**: `bench --site <sitename> run-tests --app huf --module huf.ai.tests.test_elevenlabs_convai` → `OK`, 8 tests pass.

### Step 5: Run the full suite

**Verify**: `bench --site <sitename> run-tests --app huf` → `OK`.

## Test plan

- New file `huf/ai/tests/test_elevenlabs_convai.py`: 8 unit tests on `_verify_webhook_signature` — valid accepted; missing/empty header rejected (the SEC-01 regression); missing secret; wrong signature; tampered body; expired timestamp; malformed header.
- Structural pattern: model after `huf/ai/tests/test_flow_eval.py` (plan 001) or `huf/huf/doctype/agent_chat/test_agent_chat.py`.
- Verification: per-module `OK`, then full-suite `OK`.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `grep -n "if sig_header:" huf/ai/providers/elevenlabs_convai_api.py` → no matches (fail-open path removed)
- [ ] `grep -n "_verify_webhook_signature" huf/ai/providers/elevenlabs_convai_api.py` → def + call present
- [ ] `grep -n "apiKeyLength\|agentIdLength" huf/ai/providers/elevenlabs_convai_api.py` → no matches
- [ ] `grep -n "allow_guest=True" huf/ai/providers/elevenlabs_convai_api.py` → `handle_elevenlabs_webhook` still has it; the others per the Step 3 decision (state which in your report)
- [ ] `bench --site <sitename> run-tests --app huf --module huf.ai.tests.test_elevenlabs_convai` → `OK`, 8 tests pass
- [ ] `bench --site <sitename> run-tests --app huf` → `OK`
- [ ] `git status --porcelain` shows ONLY the in-scope files modified (+ `__init__.py` if created, + README)
- [ ] `plans/README.md` status row for 004 updated to DONE

## STOP conditions

Stop and report (do not improvise) if:

- The drift check shows `elevenlabs_convai_api.py` changed since `abdd987` and the webhook auth block no longer matches the "Current state" excerpt (e.g. signature is already mandatory).
- You cannot determine the bench `<sitename>`.
- In Step 3 you cannot reach the operator AND cannot confirm whether an external public widget needs `get_signed_url`/`get_agent_id`. Apply Steps 1, 2, 4, 5 (which are unconditionally safe), leave the two endpoints' `allow_guest` UNCHANGED, and report Step 3 as deferred pending the operator's decision — do NOT guess.
- A test fails after one reasonable fix attempt, suggesting the helper logic differs from intent.

## Maintenance notes

- **Rotate credentials.** If these endpoints have been reachable in any deployed environment, the ElevenLabs API key (`AI Provider.api_key`) and the webhook secret (`Elevenlabs Settings.webhook_secret`) should be rotated — `get_signed_url` could have leaked signed URLs and the fail-open webhook could have been probed. Reference only; never print the values.
- The webhook `webhook_secret` is a Frappe Password field (good — encrypted at rest), unlike the flow_webhook key in plan 003.
- Reviewer should scrutinize: (1) the webhook returns `forbidden` BEFORE any `Agent Run` insert when the signature is missing/invalid; (2) `_verify_webhook_signature` never raises (all parsing in try/except); (3) no secret/signature value is logged; (4) the Step 3 decision is recorded and consistent with the operator's answer.
- Follow-up (deferred): consider a dedicated low-privilege user for the `ignore_permissions=True` `Agent Run` insert at line 187 rather than a blanket bypass — relates to plan 005's guest-permission theme.
