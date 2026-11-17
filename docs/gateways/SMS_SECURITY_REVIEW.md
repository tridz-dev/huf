# SMS Gateway Adapter Security Review (HUFCRM-02)

Status: review completed (agent + Opus reviews passed); SMS gateway re-enabled (HUFCRM-02).

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
- CLOSED: inbound now uses Twilio's real scheme: base64(HMAC-SHA1(auth_token, full URL + POST params sorted by key, key immediately followed by value)), constant-time compare; the body-only HMAC path is removed. JSON bodies: the URL must carry `bodySHA256=<hex sha256(body)>`, which is verified, and the signature covers the URL. The URL is `webhook_base_url` + request path/query when configured, else X-Forwarded-Proto/Host only if `trusted_proxy` is set, else the server-seen request URL; if it cannot be determined inbound is rejected. Default-port variants of the URL are also tried (as Twilio's SDKs do).
- Replay: Twilio's signature has no timestamp/nonce, so a captured valid request can be replayed byte-for-byte. Mitigation is dedupe on MessageSid by gateway ingress; replays of a request without a MessageSid get a fresh uuid id and are not deduped. Use HTTPS and keep `trusted_proxy` off unless your own proxy sets the forwarded headers (otherwise an attacker could choose the signed host).
- Frappe SMS Settings gives no delivery receipt or id; status is "unknown".
- Credentials (auth_token) storage/encryption follows the gateway credential store; not reviewed here.
- Not run against a bench; tests to be run with `bench run-tests --module huf.ai.gateway_adapters.tests.test_gateway_sms`.
- HUF_INTEGRATIONS_GATEWAYS_AUDIT.md / _TODO.md referenced in the old header were not found in the worktree.

## Owner decisions (non-blocking)
- SMS provider choice for OTP/failover (Twilio, Plivo, Frappe SMS Settings, other) and who funds ongoing review.
- Whether inbound two-way SMS is wanted at all (recommended: send_only for OTP/failover).
