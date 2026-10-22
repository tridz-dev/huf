# Telegram Mini App API

Backend for the admin cockpit Mini App. Code: `huf/ai/telegram_miniapp_api.py`. Auth model and cockpit rules:
`telegram-admin-cockpit.md`.

## Auth and transport

1. The Mini App POSTs `Telegram.WebApp.initData` to
   `/api/method/huf.ai.telegram_admin.telegram_miniapp_auth` (`init_data`, `gateway`) and receives
   `{token, expires_in: 900, role_scope, gateway}` (Frappe wraps it as `{"message": {...}}`).
2. Every call below sends the token in header `X-Huf-Tg-Token: <token>` (or a `token` param; `Bearer ` prefix
   tolerated). Endpoints are `allow_guest` only because the token is the credential.
3. Each call re-reads the live binding (revocation and Admin downgrade apply immediately) and runs as the
   bound Frappe user under normal permissions. Same origin, no CORS.

Base path: `/api/method/huf.ai.telegram_miniapp_api.<name>`. Frappe wraps every response as `{"message": X}`.
`X` is always one of:

```
{"ok": true,  "data": {...}}
{"ok": false, "error": {"code": "<code>", "message": "<safe text>"}}
```

HTTP status mirrors the code: `unauthorized` 401 (missing/expired/revoked token, binding gone: reopen via
initData auth), `permission_denied` 403, `not_found` 404, `invalid` 400, `refused` 400 (denied DocType,
expired/used confirmation), `rate_limited` 429, `internal` 500. Rate limits: 60 calls/min per Telegram user,
120/min per IP.

## Endpoints

| Endpoint | Method | Params | `data` |
|---|---|---|---|
| `me` | GET/POST | - | `{frappe_user, full_name, role_scope, gateway, telegram_user_id}` |
| `config` | GET/POST | - | `{gateway, bot_name, role_scope, session_ttl, confirm_ttl, limits:{search_max, audit_max}, features:{search, approvals, digest, act, audit, audit_all}}` (`act` = Operator+, `audit_all` = Admin) |
| `search` | GET/POST | `doctype`, `text=""`, `limit=10` (max 25) | `{doctype, items:[{name, title}]}` |
| `get_doc_summary` | GET/POST | `doctype`, `name` | `{doctype, name, title, workflow_state, status, docstatus, modified, fields:[{fieldname,label,fieldtype,value}], actions:[str], desk_url}` (`actions` empty below Operator) |
| `approvals` | GET/POST | - | `{items:[{doctype, name, state, actions:[str]}]}` |
| `act_prepare` | POST | `doctype`, `name`, `action` | `{nonce, description, expires_in: 300, action:{doctype,name,action}}` (Operator+; action must be a currently available workflow transition; nothing is changed) |
| `act_confirm` | POST | `nonce` | `{result: "Done: ... is now <state>"}` (single use, bound to the Telegram user and the Mini App; executes via the cockpit `execute`, writes `Telegram Admin Audit`) |
| `digest` | GET/POST | - | `{text, approvals:[{doctype,name,state}], actions_24h}` |
| `audit` | GET/POST | `limit=20` (max 50) | `{scope: "own"|"all", items:[{action, frappe_user, reference_doctype, reference_name, result, creation}]}`; Admin sees all, others only their own rows |
| `revoke_token` | POST | - | `{revoked: true}` (logout; token dies immediately) |

Notes:
- DocTypes in `telegram_admin.DENY_DOCTYPES`, child tables and singles are refused (`refused`).
- Summary fields exclude Password/Attach/Table/Code/JSON fields, permlevel > 0 fields and secret-like field names.
- A nonce issued by the chat cockpit cannot be confirmed from the Mini App and vice versa.
- After `unauthorized`, discard the token and re-run initData auth.
