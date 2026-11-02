# Telegram web access (one-tap sign-in)

A Telegram user who has linked their account (Telegram Admin Binding) can tap a Mini App button and be
signed into Frappe as their linked user. Telegram-signed `initData` plus the active binding are the only
trusted authentication source. This page covers the sign-in exchange (`huf/ai/telegram_web_access.py`);
what a Telegram session may do afterwards is enforced separately (`telegram_web_access_enforce`).

## Exchange flow

`POST /api/method/huf.ai.telegram_web_access.exchange` with `init_data`, `gateway`, optional `to`
(JSON or form).

1. Rate limit per IP (30/min), then per Telegram user (10/min). `Origin` must equal the site origin (or, if absent, `Sec-Fetch-Site: same-origin`); the launch page's fetch always sends `Origin`.
2. Gateway must be an enabled Telegram gateway with `telegram_web_access_enabled`.
3. `to` is normalized and must equal or sit under an allowed prefix (path-segment boundary). Empty `to`
   goes to the first allowed prefix. Rejected: `//`, backslash, schemes, `@`, control characters, `..`
   and any percent-encoded form of those. Validated before the initData is consumed.
4. `initData` HMAC is checked with the gateway bot token, max age 120 s, chat type must be `private`,
   `sender` or absent.
5. Single use: the hash (and `query_id` when present) is claimed in the cache with `SET NX EX`; a second
   use fails.
6. The active binding is looked up strictly by Telegram user id + gateway.
7. Eligibility: never the `Administrator` user, `Guest`, disabled users or non System User types. Users
   holding the `System Manager` or `Administrator` role are refused unless `telegram_web_allow_privileged`
   is on. The same check is repeated (cached ~30 s) on every request, so a user who later gains one of
   those roles loses the Telegram session.
8. `LoginManager.login_as(user, session_end=now+hours, audit_user="telegram:<id>")` creates a normal
   Frappe session. The `sid` is only ever set as an HttpOnly cookie (`Secure` when `request.scheme` is https
   or the site's `host_name` starts with `https://`; a client-supplied `X-Forwarded-Proto` is never trusted
   on its own, Frappe applies it only when the bench runs with proxy handling; `max_age` = session length,
   capped at 720 hours). It is never
   in the URL, JSON or logs. The session data carries `tg_origin = {binding, gateway, tg_id,
   web_access_version: 1}`. The write switch is not stored in it; the guard reads it live from the gateway.
9. A request that already carries a valid Telegram-origin session for the same user and gateway only gets
   the redirect.

Response: `{"ok": true, "redirect": "<path>"}`. Every failure is HTTP 403 `Not authorized`; the reason code
is only in the log (`reason`, `sha256(hash)[:12]`, tg id, binding, outcome) and in a Telegram Admin Audit
row (`web_login`).

## Gateway fields

| Field | Meaning |
| --- | --- |
| `telegram_web_access_enabled` | Master switch (default off). |
| `telegram_web_allowed_paths` | One route prefix per line; `/` alone is not accepted. |
| `telegram_web_session_hours` | Session length, default 24, between 1 and 720 (validated on save, capped again at login). |
| `telegram_web_allow_privileged` | Lets System Manager and Administrator role holders in. Unsafe: for local or non-sensitive environments only. |
| `telegram_web_allow_writes` | Off (default) = read-only: no changes through the guard's allowed methods (viewing may still record view logs or prepared reports). On = a denylist: everything the user's Frappe permissions allow except the always-blocked set listed in the enforcement doc. Read live from the gateway (cached up to 30 seconds), so a change also applies to sessions that are already open. |
| `telegram_web_extra_read_methods` | Extra `/api/method` names allowed in read-only mode. |

## Policy: what `login_as` skips and runs

Skipped versus a password login: `before_login` hooks, password check, two-factor authentication, forced
password reset and login-attempt throttling (accepted by the owner; the UI warns). Still run: `on_login`
hooks, IP restriction (`validate_ip_address`), allowed login hours, `on_session_creation` hooks, normal
session expiry and `session_end`, and Frappe's login metadata.

Helpers for other modules: `session_marker(session_data)`, `is_tg_session()`, `normalize_target(path)`,
`allowed_prefixes(gateway_doc)`.

Note: Frappe checks `session_end` only when a session is read from the cache; a session loaded from the
database after a cache miss is accepted once and then expires on the next cached read. The enforcement
hook should therefore compare `session_end` itself.

## What the settings do and do not limit

- `telegram_web_allowed_paths` limits page navigation only. API access (`/api/...`) covers whatever the
  bound user's Frappe permissions allow, within the guard's rules (default read list, blocked methods and
  doctypes). It is not a data-scope boundary.
- Read-only means no changes through the guard's allowed methods. Reads can still write side effects such as
  view logs or prepared-report results.
- Writes-on is opt-in and a denylist, not an allowlist.
- Realtime: the socket.io server authenticates a session by calling `frappe.realtime.get_user_info` over HTTP
  with the sid cookie. That method is not in the default read list, so a Telegram session gets no realtime
  connection unless it is added as an extra read method. Verified from the Frappe 16 source
  (`realtime/middlewares/authenticate.js`); pages degrade to no live updates. Not exercised in a live browser.

## Other sessions of the same user

Opening a page through Telegram calls `LoginManager.login_as`, which runs Frappe's `clear_active_sessions`.
When `deny_multiple_sessions` is on (site config or System Settings), this signs the person out of their other
browser sessions (their ordinary session is evicted; this is Frappe's single-session policy applied to the
new login). It does nothing when the setting is off. This is kept deliberately: bypassing it for Telegram
would defeat the site's single-session policy. The settings UI says: "Opening a page through Telegram can
sign this person out of their other browser session depending on the site's simultaneous-session setting."

## Framing

`/tg_open` refuses to run inside a frame (client-side check, which also blocks Telegram Web). No
`frame-ancestors` / `X-Frame-Options` header is sent: Frappe www pages have no cheap per-page header hook
and the guarantee would add little over the in-page check. No SRI on Telegram's script, since it changes.
