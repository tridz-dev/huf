# SMS Gateway Adapter Security Review (HUFCRM-02)

Status: review completed (agent + Opus reviews passed). The SMS adapter is re-enabled (HUFCRM-02); its 26 tests were run on a real bench.

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

## Credential keys (`huf/ai/gateway_adapters/sms.py`)
- `mode` (required): `twilio` (send and inbound), `send_only` (Twilio send, inbound always rejected) or `frappe_sms` (Frappe SMS Settings, inbound rejected).
- `account_sid`, `auth_token`, `from_number`: Twilio credentials (`twilio` and `send_only`); inbound needs `account_sid` and `auth_token` in `twilio` mode.
- `webhook_base_url`: public origin Twilio calls (for example `https://crm.example.com`); used with the request path and query to rebuild the signed URL. Recommended behind a proxy.
- `trusted_proxy`: `1`/`true`/`yes` only if your own proxy sets X-Forwarded-Proto/Host; otherwise the forwarded headers are ignored.
- Inbound signature: `X-Twilio-Signature` = base64(HMAC-SHA1(auth_token, URL + POST params sorted by key, each key followed by its value)), constant-time compare. For JSON bodies the URL must carry `bodySHA256=<hex sha256(body)>`, which is verified.

## Residual risks
- CLOSED: inbound now uses Twilio's real scheme: base64(HMAC-SHA1(auth_token, full URL + POST params sorted by key, key immediately followed by value)), constant-time compare; the body-only HMAC path is removed. JSON bodies: the URL must carry `bodySHA256=<hex sha256(body)>`, which is verified, and the signature covers the URL. The URL is `webhook_base_url` + request path/query when configured, else X-Forwarded-Proto/Host only if `trusted_proxy` is set, else the server-seen request URL; if it cannot be determined inbound is rejected. Default-port variants of the URL are also tried (as Twilio's SDKs do).
- Replay: Twilio's signature has no timestamp/nonce, so a captured valid request can be replayed byte-for-byte. Mitigation is dedupe on MessageSid by gateway ingress; replays of a request without a MessageSid get a fresh uuid id and are not deduped. Use HTTPS and keep `trusted_proxy` off unless your own proxy sets the forwarded headers (otherwise an attacker could choose the signed host).
- Frappe SMS Settings gives no delivery receipt or id; status is "unknown".
- Credentials (auth_token) storage/encryption follows the gateway credential store; not reviewed here.
- HUF_INTEGRATIONS_GATEWAYS_AUDIT.md / _TODO.md referenced in the old header were not found in the worktree.

## Owner decisions (non-blocking)
- SMS provider choice for OTP/failover (Twilio, Plivo, Frappe SMS Settings, other) and who funds ongoing review.
- Whether inbound two-way SMS is wanted at all (recommended: send_only for OTP/failover).
