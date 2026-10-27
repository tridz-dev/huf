# Microsoft Teams gateway: routes, configuration and environment (slice 1)

Verified from the code on branch `wp/teams-t15` (from `feat/teams-p0`). Contract version
`teams-p0/1` (`huf/ai/gateways/teams_contract.py`).

## 1. HTTP routes

| Route | Method | Auth | Purpose |
|---|---|---|---|
| `/api/method/huf.ai.gateway_webhook.handle_gateway_webhook?gateway_name=<name>` | POST (GET accepted) | Guest allowed; the Bot Framework bearer JWT is verified in `TeamsGatewayAdapter.verify_inbound` | Bot Framework messaging endpoint. 400 missing `gateway_name`, 404 unknown gateway, 403 disabled, 401 failed verification. Rate limit 100 requests / 60 s per `gateway_name` |
| `/huf/link-account?p=teams&token=<token>` | browser (SPA page) | Huf login required | Self-link confirmation page. `p=teams` selects Teams wording. Calls `preview_teams_link` (GET) then `confirm_teams_link` (POST), which creates a **Pending** link and queues a Yes/No card to the person's personal chat |
| `/api/method/huf.ai.tools.teams_webhook.handle_teams_outgoing_webhook` | POST | HMAC, verified inside the handler | Legacy Teams Outgoing Webhook. Not part of this work, not extended; public channels only |

The webhook route is on `EXEMPT_AUTH_ROUTES`. An `auth_hooks` entry (`exempt_gateway_webhook_auth`)
authenticates the request as the disabled, role-less technical user `gateway-webhook@huf.system`
only so Frappe's core two-part `Authorization` check passes; real verification is the JWT check.

Synchronous invoke answers: for `adaptiveCard/action` activities, the card-action filter sets
`frappe.local.gateway_response_override` and `handle_gateway_webhook` returns it as the raw HTTP
response (status 200, JSON). Other invoke names are tagged `ignored` and acknowledged normally.

There is **no OAuth redirect URI in slice 1.** No authorization-code flow, no SSO, no Graph
consent. Nothing needs to be registered under "Redirect URIs" in the Entra app, and the manifest
has no `webApplicationInfo`. The link page is a Huf page reached from a chat link; it is not an OAuth callback.

Exact URL list that Microsoft or Huf users interact with:

- Messaging endpoint (Azure Bot): the webhook URL above.
- Link page: `<site URL>/huf/link-account?p=teams&token=<token>`.
- Manifest URLs: website `<site>`, privacy `<site>/privacy`, terms `<site>/terms` (the last two are
  not served by Huf), `validDomains` = site host.
- Outbound (called by Huf): see section 6.

## 2. Whitelisted methods

All are under `huf.ai.gateways.<module>.<function>`. "SM" = System Manager role.

| Method | HTTP | Permission |
|---|---|---|
| `teams_tenant.get_teams_settings(gateway)` | GET/POST | SM, or read on the Gateway |
| `teams_tenant.save_teams_settings(gateway, allowed_tenants, bot_handle, app_package_version, private_output_policy, help_text_override)` | POST | SM, or write on the Gateway. Only provided fields change. Invalid GUID or unknown policy raises ValidationError |
| `teams_identity.preview_teams_link(token)` | GET | Logged-in, enabled, non-Guest, non-Administrator user. Changes nothing. Returns `tenant_id` (show prominently), `external_id`, and `display_label_untrusted` (Teams display name, attacker-controllable; `person_label` is the same value kept for compatibility) |
| `teams_identity.confirm_teams_link(token)` | POST | Same as above; token must verify and be unused. Returns `{linked: false, pending: true}` after queuing the Teams confirmation card; if the card cannot be queued the Pending row is revoked and a ValidationError is raised. A newer attempt for the same Teams person supersedes older Pending rows |
| `teams_identity.list_teams_links(gateway)` | GET/POST | SM, or write on the Gateway. Up to 500 rows |
| `teams_identity.link_teams_user(gateway, tenant_id, aad_object_id, user)` | POST | SM, or write on the Gateway. User must be enabled and not Guest |
| `teams_identity.revoke_teams_link(name)` | POST | SM, or write on the link's Gateway |
| `teams_notify.send_teams_notification(gateway, user, text, card, dedupe_key, dedupe_hours)` | POST | The target user themselves, or SM, or write on the Gateway. Not Guest |
| `teams_manifest.download_teams_app_package(gateway_name, version)` | GET | SM, or write on the Gateway. File download |
| `teams_diagnostics.teams_diagnose(gateway_name)` | GET/POST | SM, or write on the Gateway; gateway must be a Teams gateway |
| `teams_diagnostics.teams_support_bundle(gateway_name)` | GET/POST | Same |

`send_teams_notification` returns `{success, outbox, deduped[, error]}` and never throws plain-language
failures: unlinked user, no known service URL, disabled gateway and refused chat creation come back as
`success: false`. Text is limited to 3000 characters (control characters removed); a card must be an
object with `type: "AdaptiveCard"` and at most 20000 bytes of JSON. It targets a Huf **user** with a
Linked identity, never a raw Entra id or email; it reaches the stored installed personal chat, or
creates a one-to-one chat with the known service URL. It never creates group chats.

## 3. Scheduler and doc events (`huf/hooks.py`)

| Hook | Entry | Behaviour |
|---|---|---|
| `scheduler_events["cron"]["*/1 * * * *"]` | `huf.ai.gateways.teams_outbox.retry_due` | Enqueues delivery for up to 50 `Pending` outbox rows whose `next_attempt_at` has passed |
| `scheduler_events["daily"]` | `huf.ai.gateway_service.purge_old_rejected_gateway_events` | Generic: deletes `Rejected` Gateway Events older than 30 days. Only Rejected rows |
| `doc_events["Agent Execution Approval"]["after_insert"]` | `huf.ai.gateways.teams_actions.on_approval_inserted` | Enqueues `notify_approvers_job` after commit; sends approval cards to approvers who have a linked identity and an installed personal chat (alongside the existing generic handler) |
| `auth_hooks` | `gateway_webhook.exempt_gateway_webhook_auth` | See section 1 |

Gateway hooks registered for provider `microsoft teams` (modules listed in
`huf/ai/gateways/_registered.py`), in `pre_ingest_filter` order: 10 install/uninstall
(`teams_refs`), 20 tenant allowlist (`teams_tenant`), 30 card actions (`teams_actions`),
40 commands (`teams_help`). Card actions of kind `idlink` (link confirmation, `teams_identity_confirm`) go through the card-action filter and its handler registry.

Filter semantics (`hooks.call_filters`, used by `gateway_service.ingest`): filters run in ascending
priority and evaluation **stops at the first filter that returns False**, so later filters (card
actions, commands) never run for an event an earlier one rejected and cannot clear its reason. A
filter that raises is treated as False (fail closed) and the reason becomes `filter_error` unless the
filter set one. When a filter sets `frappe.flags.gateway_filter_reason` the event is stored as a
Gateway Event with status Rejected and that reason (`tenant_not_allowed`, `filter_error`); with no
reason (commands, installs of allowed tenants) the ingest returns `{"filtered": true}` and no event is
created. Duplicate activity ids short-circuit before any filter runs. Also: `on_event_received` (reference upsert), `resolve_run_user` and
`on_run_success` (`teams_identity`), `resolve_conversation_key` and `resolve_reply_target`
(`teams_privacy`). The Teams adapter is built with the gateway name (`gateway_webhook` passes it
when the adapter constructor accepts it), so conversation-reference lookups and outbox keys are
scoped to that gateway.

## 4. Configuration

### Credentials (Integration Settings, service `microsoft_teams`)
`app_id`, `app_password`, `tenant_id`; all required. Stored encrypted as Integration Credential rows.

### Teams Gateway Settings (one record per Gateway, name = gateway)
Editable by System Manager. Missing record means defaults. Read through a 30-second in-process cache,
cleared on save.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `allowed_tenants` | Small Text | empty | Tenant GUIDs, one per line; empty = home tenant only |
| `bot_handle` | Data | empty | Stored; not read by any current code path |
| `app_package_version` | Data | empty | Informational; shown by the `app_package` check |
| `private_output_policy` | Select | `Private when records touched` | `Always private` / `Private when records touched` / `Channel` (section 5) |
| `help_text_override` | Small Text | empty | Stored; **not used** by the `help` command (it always returns built-in text) |

### Gateway doctype fields that matter for Teams
`provider` = `Microsoft Teams`; `is_enabled`; `integration_settings`; `execution_user` (required to run
events; not used as the identity of Teams people); `direct_policy`, `room_policy`,
`room_sender_policy`, `mention_required`, default route/binding. `unmapped_policy` and
`private_reply_policy` are **Slack-only: ignored for Teams** (Teams never falls back to the service
user; private routing uses `private_output_policy`).

### Private output policy behaviour (rooms only; personal chats never change)
- `Always private`: every room answer goes to the asker's personal chat.
- `Private when records touched`: private if the run called any tool other than a small safe list
  (calculator, current time, knowledge search), or the run is flagged sensitive, or the run is unknown.
- `Channel`: answer in the room unless the run was flagged sensitive.
- If a private chat cannot be obtained, the answer is **not** posted to the room; a neutral note asks
  the user to open a private chat and send "hi".

### Constants (code, not settings)
Token TTL for link 10 min; connect-prompt throttle 2 min; link confirmation card session 15 min; inbound clock skew 300 s; outbox attempts 6,
backoff 30 s, 2 min, 10 min, 30 min, 2 h (a valid `Retry-After` overrides, capped 6 h); claim lease 300 s;
approval card TTL = approval expiry, else 24 h; `status` shows the last 5 runs.

## 5. Cache keys (`frappe.cache`, Redis) and in-process caches

| Key | TTL | Content |
|---|---|---|
| `teams:jwks:<metadata url>` | 24 h (also an in-process copy; forced refresh on unknown `kid`, at most once per 60 s) | Signing keys |
| `teams:token:<gateway name>` | token `expires_in` minus 300 s | Bot Connector access token (secret; Redis access = token access) |
| `huf_teams_link_nonce:<nonce>` | 10 min | Single-use marker for a link token |
| `huf_teams_link_prompt:<gateway>:<tenant>:<aad id>` | 2 min | Re-used connect link token (throttle) |
| `huf:teams:sensitive:<event or run>` | 1 h | Sensitivity flag set by `mark_sensitive` |
| `huf_teams_approval_notified:<gateway>:<approval>:<user>` | 7 days | Approval card already queued |
| `teams:notify:<hash>` | `dedupe_hours` (default 24 h) | Notification dedupe |

## 6. Environment assumptions

- Python: `PyJWT>=2.8.0`, `cryptography`, `requests`. RS256 tokens only.
- Outbound HTTPS only, no redirects followed, timeouts 5 s (metadata) / 10 s (connector):
  - `https://login.botframework.com/v1/.well-known/openidconfiguration` and the `jwks_uri` it returns (https required).
  - `https://login.microsoftonline.com/<tenant>/v2.0/.well-known/openid-configuration` (Entra-issued tokens) and `https://login.microsoftonline.com/<tenant>/oauth2/v2.0/token` (scope `https://api.botframework.com/.default`).
  - The activity `serviceUrl`, e.g. `https://smba.trafficmanager.net/<region>/`. serviceUrl allowlist: exactly `smba.trafficmanager.net`, or any host ending `.botframework.com` or `.teams.microsoft.com` (other `*.trafficmanager.net` hosts are refused); https, port 443 only; IPs and encoded paths rejected.
- Inbound: Microsoft must reach the public HTTPS endpoint. Site `encryption_key` must exist (it signs link tokens).
- Commercial global cloud only; national clouds are not supported.

## 7. Doctypes added

`Teams Gateway Settings`, `Teams Conversation Reference` (name = hash of gateway+tenant+conversation),
`Teams Outbound Message`, `Teams Action Session`; shared `Gateway Identity Link` (provider
`Microsoft Teams`, `team_id` = tenant GUID, `external_id` = Entra object id). All five allow only
System Manager. `Gateway`, `Gateway Event` and `Integration Settings` are System-Manager-only for generic resource access.

## 8. Troubleshooting map

| Symptom | Check |
|---|---|
| Azure "messaging endpoint" test or all messages 401 | `credentials_present`; audience = `app_id`; issuer/tenant; clock; `serviceUrl` mismatch. Gateway Event rows are not created for 401 (verification precedes ingest) |
| Event Rejected `tenant_not_allowed` | `allowed_tenants` / home tenant |
| Rejected "Sender is not approved" | `direct_policy` / Access Entries (ADMIN_SETUP.md 3.3) |
| User asked to connect every time | no Linked row; check "Teams people" |
| Event Rejected `filter_error` | A Teams filter raised; the event is rejected (fail closed). Check the Error Log |
| Answers never arrive | `outbox` check: Pending (workers/scheduler; also transient failures incl. transport errors/timeouts waiting for backoff), Failed (permanent 4xx; not retried), Dead (6 attempts exhausted) |
| Link stays Pending | The person has not clicked Yes in their personal chat (15 min), or the card was not delivered; send `connect` again |

Outbox delivery (`teams_outbox`): the default sender builds a bot token provider from the row's
gateway credentials and posts with `Authorization: Bearer`. Transient failures (HTTP 0 transport
errors, 408, 429, 5xx, timeouts) go back to Pending with backoff up to 6 attempts, then Dead; other
errors mark the row Failed. A POST that succeeded but timed out may be retried, so a duplicate message is
possible (the Bot Connector has no idempotency key).
Reply idempotency: the key uses the inbound activity id plus text hash when the reply targets a real
inbound activity; otherwise (personal chats, ad-hoc sends) each reply gets its own nonce, so identical
text sent twice is delivered twice and only a retry of the same reply object is deduped. Delivered card
activity ids are stored on the Teams Action Session (`card_activity_id`) when the outbox payload names the
session. A redelivered card click returns a read-only invoke body (decided/expired/neutral message)
instead of the generic JSON.
