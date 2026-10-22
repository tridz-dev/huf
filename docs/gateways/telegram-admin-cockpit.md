# Telegram admin cockpit

An owner/admin "personal assistant" for Frappe/ERPNext inside the same Telegram bot that serves the
gateway. The chat cockpit is the primary client (commands, compact tables, signed inline buttons, digests).
A Mini App is secondary, for dense views. Code: `huf/ai/telegram_admin.py`; doctypes `Telegram Admin
Binding` and `Telegram Admin Audit`.

## Threat model

| Threat | Mitigation |
| --- | --- |
| Telegram user claims to be a Frappe user | A binding is created only from a one-time code minted by the signed-in Frappe user. Telegram-side claims (username, text) never create one. |
| Bind code guessed or brute forced | 10 chars from a 32-symbol alphabet (~50 bits), 10 min TTL, single use (atomic claim), only its SHA-256 is stored, 5 attempts per Telegram user per 10 min, 5 mints per Frappe user per 10 min. |
| Forged or tampered button | `callback_data` is HMAC-signed with the gateway's webhook-secret-derived key and bound to the chat id (`telegram_keyboards`). An invalid signature is refused. |
| Replayed, expired, or stolen confirmation | Every action button carries its own nonce (cache, 5 min TTL). The nonce is bound to Telegram user + chat + action hash, and is burned by an atomic claim on first use. A press from another user is refused and does not burn the nonce, so it cannot cancel the owner's confirmation. |
| Privilege escalation through the bot | All reads and writes run as the bound Frappe user (`run_as`) with `frappe.get_list` / `check_permission` / `apply_workflow`. Administrator and Guest are never bound or impersonated. No `ignore_permissions` on business data. `role_scope` only narrows what the cockpit offers; it never grants a Frappe permission. |
| Data leaking into group chats | Only private chats are intercepted. Group commands fall through to the normal gateway path. |
| Secret exposure | Secret-bearing doctypes are on a denylist (Gateway, Huf API Key, AI Provider, User, OAuth, the cockpit doctypes). Fields with permlevel > 0 and Password/Attach fields are never echoed. Audit arguments are redacted (`pass/token/secret/key/otp/pin/auth/cookie`) and truncated. |
| Flooding | 30 commands + presses per user per minute. Mini App auth is limited to 20 per IP per minute. |
| Mini App session theft | No Frappe session or cookie is issued. The bearer token is opaque, lasts 15 min, is stored hashed, and is re-checked against an active binding on every use. initData max age is 10 min. |

System bookkeeping (inserting the binding, inserting audit rows, deactivating a binding) uses
`ignore_permissions`, because the acting Telegram user must not need create rights on those doctypes. These
are the only such writes.

## Identity binding

1. The signed-in Frappe user calls `huf.ai.telegram_admin.create_binding_code(gateway, role_scope)`
   (POST). It is refused for Guest/Administrator and for non-Telegram gateways. `Admin` scope requires
   `is_gateway_admin`. It returns `BIND-XXXXXXXXXX` and instructions.
2. In a private chat with the bot the user sends `/start BIND-XXXXXXXXXX`, or uses the deep link
   `t.me/<bot>?start=BIND-...`. The admin handler intercepts this before pairing/admission and redeems
   the code once, for that gateway only.
3. A `Telegram Admin Binding` is inserted with telegram_user_id (unique), frappe_user, gateway, role_scope,
   private chat id, and paired_at. A `bind` audit row is written. An inactive binding for the same Telegram
   id is replaced. An active binding to a different Frappe user is refused (`/unbind` first).
4. `/unbind` (confirmed) or `revoke_binding(name)` (the owner, or a gateway admin) sets `is_active = 0`.
   Mini App tokens die with the binding.

A binding does not add the user to the gateway access list. Free-text messages still go through normal
admission and routing to the configured agent. The cockpit does not run agents.

## Roles (`role_scope`)

| Scope | Cockpit offers |
| --- | --- |
| Viewer | `/me`, `/find`, `/open`, `/approvals` (list only), `/digest`, `/help`, `/unbind` |
| Operator | Viewer + workflow transition buttons (approve/reject, ...) |
| Admin | Operator + `/audit` (still subject to read permission on Telegram Admin Audit) |

## Command set

| Command | Behaviour (always run as the bound user) |
| --- | --- |
| `/me` | Bound user, scope, gateway, and a Mini App button when an https launch URL exists |
| `/find <doctype> <text>` | `frappe.get_list` on name/title `like`, 10 rows. The doctype may contain spaces. |
| `/open <doctype> <name>` | Summary: title, workflow state, status, docstatus, up to 8 list-view fields, a Desk link, and transition buttons (Operator) |
| `/approvals` | Open `Workflow Action` rows visible to the user, with up to 5 rows of the first two transitions |
| `/digest` | Pending approvals plus cockpit actions in the last 24 h |
| `/audit` | Last 10 audit rows (Admin) |
| `/help`, `/unbind` | Help text; two-step unbind |

Only these slash commands, `/start BIND-...`, and `adm:` callbacks are intercepted. Anything else returns
`None` from the registry handler, so the existing pipeline handles it. If an unbound user sends `/help`,
it also falls through, so the cockpit is invisible to them.

## Confirm and audit flow

```
/approvals or /open -> [Approve LA-1] button   callback adm:p:<n1>|sig  (n1 -> action)
press               -> "Apply 'Approve' to Leave Application LA-1? Confirm within 5 minutes."
                       [Confirm adm:c:<n2>|sig] [Cancel adm:x:<n3>|sig]
Confirm             -> verify sig(chat) -> binding active -> rate -> consume n2 (user+chat+hash, single use)
                    -> run_as(bound user): get_doc, check_permission(read), apply_workflow
                    -> Telegram Admin Audit (ok | error, nonce hash, redacted args) -> edit message, drop keyboard
```

`Telegram Admin Audit` is append-only. The controller refuses updates and trash, and permissions grant
only read/report/export to System Manager and read/report to Huf Manager.

### Agent admin actions

The `telegram_admin` agent tool reuses the same signed-button approval. Every state change (anything except the
read-only `get_*` actions) is accepted only from a paired Admin+ owner chat and still needs a human to press
the signed Approve button; a `confirm=true` argument from the agent is ignored. Requests from any other chat are
refused with `owner_required`. Executed and refused calls (including `owner_required` and `no_admin_available`)
write `Telegram Admin Audit` rows.

## Mini App launch contract

- Launch URL: `miniapp_launch_url(binding)` returns `site_config.huf_telegram_admin_miniapp_url` or
  `<site>/huf/telegram-admin`, plus `?gw=<gateway>`. It is https only and carries no secrets.
- Auth: the Mini App POSTs `Telegram.WebApp.initData` to
  `/api/method/huf.ai.telegram_admin.telegram_miniapp_auth` with `init_data` and `gateway` (guest allowed).
  The server validates the HMAC with the gateway bot token (`telegram_miniapp.validate_init_data`, max
  age 10 min) and requires an active binding for `(user.id, gateway)`. It returns
  `{token, expires_in: 900, role_scope, gateway}`. Every failure returns the same generic
  `AuthenticationError`.
- Use: future Mini App endpoints accept `Authorization: Bearer <token>`, call `resolve_session_token`
  (which re-checks the binding), and execute inside `run_as(session["frappe_user"])`. They follow the same
  confirm/audit rules for writes. The Mini App UI is out of scope here.

## Daily digest

`send_daily_digests()` sends each active binding with a known chat id its digest, computed as that user.
Registration is pending. Add this to `huf/hooks.py`:

```python
scheduler_events = {"daily": [..., "huf.ai.telegram_admin.send_daily_digests"]}
```

## Residual risks

- Nonce and code claims use Redis `SET NX` when the cache exposes it. Otherwise (the local fallback) they
  are best-effort get-then-set.
- Captured initData can mint tokens until it is 10 min old. A holder of initData is already that Telegram
  client.
- `/find` uses `like` on name/title only. Very large tables may scan.
- Workflow approvals cover `Workflow Action` only. Non-workflow submit/cancel is not offered.
