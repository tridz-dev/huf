# SMS Gateway Adapter Security Review (HUFCRM-02)

Status: review completed by agent; owner sign-off pending.

## Findings (develop code)
1. Fail-open inbound: `verify_inbound` returned True when `auth_token` was empty or `account_sid == "frappe_sms"`; `account_sid` defaulted to `frappe_sms`, so an empty credential set accepted any unauthenticated POST (spoofed inbound SMS to the agent).
2. Mode was inferred from missing credentials.
3. `hash()`-based ids (`sms-<hash>`, `frappe-sms-<hash>`) are salted per process: unstable, collision-prone, dedupe unreliable.
4. Frappe SMS path reported `status: "sent"` with no provider receipt.
5. Twilio failure check only tested for a `sid` key (ignored `error_code`).

## Fixes
- Explicit required `mode` credential: `twilio` | `send_only` | `frappe_sms`. Unset or unknown mode: inbound rejected and send raises.
- Inbound only passes in `twilio` mode with account_sid + auth_token and a valid `X-Twilio-Signature`; `send_only` and `frappe_sms` reject all inbound. `normalize_inbound` re-verifies and raises `PermissionError`.
- Ids: real Twilio `sid`; otherwise `uuid` with prefix `...-unknown-` and Frappe status `"unknown"`.
- Failures raise; Twilio responses with missing/empty sid or `error_code` raise.
- `send_sms_message(gateway, to, body)` returns `{ok, id, status, error}` and never raises (OTP/failover).
- Tests: `huf/ai/gateway_adapters/tests/test_gateway_sms.py` (bypass tests included).

## Residual risks
- Signature scheme is HMAC-SHA1 over the raw body only. Real Twilio signs full webhook URL + sorted POST params, so genuine Twilio callbacks will not verify until the adapter has access to the public URL (request type has no URL field). Fails closed, but inbound is effectively unusable with real Twilio until fixed. Outbound/send_only is unaffected.
- No replay protection (no timestamp/nonce); dedupe relies on MessageSid.
- Frappe SMS Settings gives no delivery receipt or id; status is "unknown".
- Credentials (auth_token) storage/encryption follows the gateway credential store; not reviewed here.
- Not run against a bench; tests to be run with `bench run-tests --module huf.ai.gateway_adapters.tests.test_gateway_sms`.
- HUF_INTEGRATIONS_GATEWAYS_AUDIT.md / _TODO.md referenced in the old header were not found in the worktree.

## Owner sign-off needed
- SMS provider choice for OTP/failover (Twilio, Plivo, Frappe SMS Settings, other) and who funds ongoing review.
- Whether inbound two-way SMS is wanted at all (recommended: send_only for OTP/failover).
- Approve fixing Twilio URL-based signature before enabling inbound.
