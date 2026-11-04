# Research: Event-Driven Agent Triggers ("App Event") for HUF

**Status:** Research dossier (intake) — analysis only, no implementation.
**Date:** 2026-07-20
**Scope:** External source systems (Gmail, Google Calendar, Slack, ERPNext) firing `Agent Trigger`s of type `App Event`. Verifies current code state, documents external-system mechanics from primary docs, critically evaluates the proposed design, and recommends a phase-1 plan.

**Verification basis:** Code citations are from the checked-out task branch `task/RES-app-event-triggers` at `95daa90` (which was `origin/develop` when this worktree was created; `origin/develop` has since advanced to `b21a672`, an unrelated audio-service refactor). The unmerged draft PR #412 code was read from `origin/task/CD-B-02-webhook-manual` (tip `f739b58`).

---

## Part 1 — Current state (code-verified)

### 1.1 The `Agent Trigger` DocType: schema is ahead of the backend

`huf/huf/doctype/agent_trigger/agent_trigger.json` already declares everything the proposal needs, schema-wise:

- `trigger_type` Select options: `Schedule`, `Doc Event`, `Webhook`, `App Event`, `Manual` (`agent_trigger.json:55-59`).
- App Event fields: `app_name` Data with `depends_on: eval: doc.trigger_type == "App Event"` (`agent_trigger.json:111-116`); `event_name` Data with **no** `depends_on` (`agent_trigger.json:117-121`).
- `source_system` Data (`agent_trigger.json:152-156`), `is_virtual` Check default 0 (`agent_trigger.json:146-151`), `metadata` JSON (`agent_trigger.json:136-140`), `disabled_reason` Small Text (`agent_trigger.json:141-145`).
- Webhook fields exist too: `webhook_key` and `webhook_slug`, both **Data** (not Password), shown only for `trigger_type == "Webhook"` (`agent_trigger.json:99-110`).

**Backend reality: only `Schedule` and `Doc Event` are wired.** A repo-wide search for `App Event` / `app_event` finds only the DocType JSON, frontend types/UI (`frontend/src/types/agent.types.ts:69,91`, `TriggerModal.tsx:73`, `TriggerFieldsConfig.tsx:99-102`, mock data in `mockApi.ts:106,179`), and AGENTS.md docs. There is **no matcher, dispatcher, endpoint, or validation** for App Event. Likewise, the `Webhook` trigger fields (`webhook_key`/`webhook_slug`) have **no consumer anywhere** on develop — the Webhook endpoint only exists in the unmerged PR #412 branch (§1.3).

### 1.2 The two wired trigger types

**Doc Event** — `huf/ai/agent_hooks.py`:

- `get_doc_event_agents(event)` (lines 12-69) caches per-event trigger lists in Redis hash `huf:doc_event_agents`, filtering `frappe.get_all("Agent Trigger", filters={"trigger_type": "Doc Event", "disabled": 0, "doc_event": event})` (lines 21-30). The only `trigger_type` filter in the file is `"Doc Event"`.
- Cache invalidation is via hooks, not the controller: `huf/hooks.py:192-196` maps `Agent Trigger` `after_insert`/`on_update`/`on_trash` → `clear_doc_event_agents_cache` (`agent_hooks.py:72-77`).
- `run_hooked_agents(doc, method)` (lines 80-139) is bound to a wildcard `"*"` DocType for 14 lifecycle events in `huf/hooks.py:175-205`. It matches on `reference_doctype` + `doc_event`, evaluates `condition` via `safe_eval` (line 102), and registers a closure on `frappe.db.after_commit` (line 139) so agents enqueue only after commit.
- Duplicate prevention: Redis lock `huf:lock:{agent}:{doctype}:{docname}:{event}` with 30s TTL (lines 114-118) — the only dedupe mechanism in the trigger system.
- Enqueue: `enqueue(run_agent_for_doc, queue="long", job_id=f"run-agent-{agent}-{doctype}-{name}-{method}-{uuid4()}", ...)` (lines 121-136).
- `run_agent_for_doc` (lines 141-299) sets user to the initiating user, builds the prompt (event + doc identifiers + optional `prompt_field` content + truncated doc JSON + OCR'd attachments), and resolves conversation identity (lines 206-216): `channel = channel_id or "doc_event"`; `external_id = initiating_user or doc.owner or doc.modified_by` if `agent.persist_user_history`, else `f"shared:{agent_name}"`. Final dispatch: `run_agent_sync(..., channel_id=channel, external_id=external_id, files=files)` (line 296).

**Schedule** — `huf/ai/agent_scheduler.py:6-56`: queries `trigger_type == "Schedule"` with `next_execution <= now`, runs `run_agent_sync` (line 36), recomputes `next_execution` from `scheduled_interval × interval_count`, commits. Wired in `huf/hooks.py:227-244` under `scheduler_events.all` (runs every ~4 minutes). Other scheduler entries worth reusing: `daily`, `hourly` (already used for MCP auto-sync and OAuth token refresh), and a `*/1 * * * *` cron.

### 1.3 The unmerged draft PR #412 (Webhook + Manual) — `origin/task/CD-B-02-webhook-manual`

`huf/ai/agent_trigger_api.py` (exists **only** on that branch; tip commit `f739b58`):

- `agent_trigger_webhook(slug, webhook_key)` — `@frappe.whitelist(allow_guest=True)`. Resolves enabled Webhook triggers by `webhook_slug` with a `disabled=0` filter and ambiguity check; validates the key fail-closed with `hmac.compare_digest` (`_webhook_key_is_valid`); hard-caps the raw body (`MAX_RAW_BODY_LENGTH = 4 × MAX_PAYLOAD_LENGTH = 80 KB`) before parsing; builds an explicitly-untrusted prompt; runs as the **trigger owner** via `frappe.set_user`; enqueues `run_agent_sync` with `channel_id="webhook"`, queue `"long"`, UUID-suffixed job id.
- `run_trigger(trigger_name, prompt)` — authenticated Manual runner: `frappe.has_permission` + `has_capability(user, "agent.use")`, type/disabled checks, synchronous `run_agent_sync` with `channel_id="manual"`.
- Conversation identity helper `_resolve_external_id` mirrors `run_agent_for_doc`'s `persist_user_history` logic.
- Notably: the security pattern is copied from `flow_api.py` (see §1.4); the branch's own commit message documents review fixes (owner identity, deterministic slug lookup, raw body cap).

**Gaps in #412 relevant to App Event:** `webhook_key` remains a **Data** field in the DocType JSON (plaintext, visible in form/list views and API reads) — the proposal's Password-field correction is right. Key is passed as a plain parameter (query/form), not HMAC-signed — acceptable for a shared-secret model but not for Slack/Google-style signing (Part 2).

### 1.4 Existing inbound-webhook precedents

- **Flow webhook** — `huf/ai/flow_api.py`: `_webhook_key_is_valid` (lines 332-353) fails closed, requires entry node type `trigger.webhook`, `hmac.compare_digest` on the configured `config.auth`. `flow_webhook(flow_id, webhook_key)` (lines 356-418) is `allow_guest=True`, throws `AuthenticationError` on bad key, parses JSON body → form → form_dict, creates a Flow Run with `trigger_type="Webhook"`, enqueues `huf.ai.flow_engine.run_flow` (lines 409-413). Auth is against the flow definition, not Agent Trigger.
- **Telegram** — `huf/ai/tools/telegram_webhook.py`: `handle_update()` (lines 53-101), `@frappe.whitelist(allow_guest=True, methods=["POST"])`, doc identified by `?doc=` param; secret validated via `settings.get_password("telegram_webhook_secret")` against the `X-Telegram-Bot-Api-Secret-Token` header with `secrets.compare_digest` — but **skipped entirely if no secret is configured** (fail-open; weaker than flow/#412 fail-closed). Immediate 200; work enqueued (`process_telegram_update`, lines 104-179) which runs as Administrator and dispatches `run_agent_sync(..., channel_id="telegram", external_id=str(chat_id))`.
- **SSE streaming** is a page renderer (`website_route_rules` in `huf/hooks.py:62-75`); inbound webhooks in HUF are whitelisted methods, not route rules.

### 1.5 Google auth today: self-managed refresh tokens, no `google_services` OAuth

- The brief's claim about "the google_services Frappe app (Google OAuth)" does **not** hold here: `google_services` is not referenced anywhere in this repo (no imports, no hooks, no `pyproject.toml` dependency; `required_apps` in `huf/hooks.py:15` is commented out). On this machine it exists only as sibling checkouts inside frappe_docker dev benches, and it is an unrelated **Google Places** app (API-key auth via `frappe.conf.get("PLACE_API_KEY")`; zero OAuth code). It can mint nothing for HUF.
- HUF's actual Google credential path is `huf/ai/tools/credentials.py:21-74` (`require_credential(service, key)`): `Integration Settings` child-table credentials decrypted via `get_password("value")`, env-var fallback. Gmail/Calendar/Meet/Sheets/Drive tools each POST a stored `refresh_token` to `https://oauth2.googleapis.com/token` on every call (e.g. `gmail.py:9-52`, `google_meet.py:11-24`, `google_calendar.py:11-28`). Refreshed access tokens are **not persisted** (see comment in `gmail.py` ~line 37 and the TODO in `credentials.py:4-5`). No scopes are declared in code — HUF consumes refresh tokens provisioned externally, so available scopes are whatever the token was issued with. There is **no OAuth consent flow in HUF**, and no push/watch usage anywhere — all Google tools are request/response only.

### 1.6 Dispatch plumbing that App Event can reuse

- `run_agent_sync` signature — `huf/ai/agent_integration.py:631-653`: `(agent_name, prompt, provider, model, channel_id, external_id, conversation_id, parent_run_id, orchestration_id, response_format, flow_run_id, flow_node_id, run_kind, prompt_template, prompt_version, parent_conversation_id, invoked_by_agent, prompt_cache_options, files, skip_user_message)`. `channel_id` defaults to `"api"` (lines 657-658). Endpoint is `allow_guest=True` but rejects Guest unless the agent has `allow_guest` (line 665), plus a per-agent user check (line 668) — which is why #412 runs webhooks as the trigger owner instead of Guest.
- Conversation identity: `ConversationManager(agent_name, channel, external_id)`; session id resolves to `f"{channel}:{external_id}"` when no explicit session id (`conversation_manager.py:325-334`); `get_or_create_conversation` reuses the latest active conversation for `(agent, session_id)` (lines 354-394).
- Seeding: `huf/ai/app_seeding/` can ship `huf/triggers/*.json` from any app (`seeder.py:24-31`, `loaders.py:185-186`) — so Virtual/App-Event trigger definitions can be app-seeded, but seeding only creates documents; nothing executes them.
- Confirmed absent: no event envelope, no `event_id` dedupe, no `source_system` consumer, no generic inbound event bus (grep for `dedupe`/`envelope`/`event_id`/`source_system` finds only the unused DocType field and unrelated calendar-event IDs).

---

## Part 2 — External-system mechanics (primary docs)

### 2.1 Gmail: `users().watch()` + Cloud Pub/Sub push

Primary: [Gmail API push notifications guide](https://developers.google.com/workspace/gmail/api/guides/push).

- Setup: create a Pub/Sub topic, create a push (webhook) or pull subscription, and grant **publish** rights on the topic to `gmail-api-push@system.gserviceaccount.com`.
- Register: `POST https://www.googleapis.com/gmail/v1/users/me/watch` with `{topicName, labelIds, labelFilterBehavior}`. Response: `{historyId, expiration}`. A successful watch immediately sends one notification.
- **Expiry/renewal: you must call `watch` at least once every 7 days or you stop receiving updates; Google recommends calling it once per day.** The `expiration` field carries the deadline.
- Notification shape: a Pub/Sub push POST whose body is `{message: {data, messageId, publishTime}, subscription}`. `message.data` is base64url JSON: `{"emailAddress": "...", "historyId": "..."}`. **No email content is included** — you must call `history.list` with your last known `startHistoryId` to learn what changed, then store the new historyId.
- Ack: push delivery is acked by an HTTP success (e.g. 200); Pub/Sub retries unacked messages later.
- Limits/reliability: **max 1 notification/second per watched user** (excess dropped); notifications "usually" arrive within seconds but can be delayed or dropped in extreme situations — Google explicitly tells you to keep a periodic `history.list` reconciliation loop. Also: beware notification loops (acting on a notification causing another one).

Push auth (separate primary doc): [Authenticate push subscriptions](https://cloud.google.com/pubsub/docs/authenticate-push-subscriptions) — with auth enabled, Pub/Sub signs an **OIDC JWT** and sends it in the `Authorization: Bearer` header. The receiver must validate the signature (Google certs) and the `email`/`aud` claims. Setup requires a push-auth service account and granting `iam.serviceAccountTokenCreator` to `service-{PROJECT_NUMBER}@gcp-sa-pubsub.iam.gserviceaccount.com`. A static shared key in the URL is **not** the sanctioned mechanism (it works as an application-level check but proves nothing about the sender).

### 2.2 Google Calendar: push notification channels

Primary: [Calendar API push notifications guide](https://developers.google.com/workspace/calendar/api/guides/push).

- Register per resource: `POST /calendar/v3/calendars/{id}/events/watch` with `{id (unique ≤64 chars, UUID recommended), type: "web_hook", address (HTTPS, valid non-self-signed cert required), token (optional ≤256 chars, echoed back in every notification — the intended anti-spoof mechanism), expiration (optional ms epoch)}`. Watchable resources: Acl, CalendarList, Events, Settings.
- Response: `{kind: "api#channel", id, resourceId, resourceUri, token, expiration}` — store `resourceId`; it's required to stop the channel.
- First message is a `sync` notification (`X-Goog-Resource-State: sync`, `X-Goog-Message-Number: 1`); it can arrive before the watch response.
- **Notifications carry no body** — headers only: `X-Goog-Channel-ID`, `X-Goog-Channel-Token`, `X-Goog-Channel-Expiration`, `X-Goog-Resource-ID`, `X-Goog-Resource-URI`, `X-Goog-Resource-State` (`sync`/`exists`), `X-Goog-Message-Number` (increasing but not sequential). You must call the API to learn what actually changed (delta sync with sync tokens).
- **Renewal: there is no automatic renewal.** When a channel nears expiry you create a **new** channel (new `id`); expect an overlap window with both channels active → duplicate notifications. Third-party docs put the practical max lifetime at ~1 week (default TTL 604800s), consistent with Google's "most restrictive value wins" rule.
- Respond 200/201/202/204/102; 500/502/503/504 → retry with exponential backoff; any other status = failure. Stop via `POST /calendar/v3/channels/stop` with `{id, resourceId}`.

### 2.3 Slack: Events API

Primary: [Slack Events API](https://docs.slack.dev/apis/events-api/) and [Verifying requests from Slack](https://docs.slack.dev/authentication/verifying-requests-from-slack/).

- Delivery: HTTP POST per event (or Socket Mode — a WebSocket alternative that avoids a public endpoint entirely). Envelope: `{type: "event_callback", team_id, api_app_id, event: {...inner...}, event_id, event_time, authorizations, ...}`. `event_id` is **globally unique** — a natural dedupe key. Inner `event.type` is the event name (e.g. `message.channels`, `reaction_added`).
- **Handshake: when configuring the request URL, Slack POSTs `{type: "url_verification", challenge}` and the endpoint must return the challenge value.** The endpoint must handle this before any signature check matters.
- **Verification: HMAC-SHA256, not a static key.** Compute `'v0:' + X-Slack-Request-Timestamp + ':' + raw_body`, HMAC with the app's **signing secret**, hex digest prefixed `v0=`, compare to `X-Slack-Signature` with a constant-time compare; reject if the timestamp is more than ~5 minutes old (replay protection). Requires the **raw body before parsing**. (The legacy `token` field is deprecated.)
- Ack discipline: respond HTTP 200 **within 3 seconds**, process asynchronously. Retries: 3 attempts (immediate, +1 min, +5 min) with `x-slack-retry-num` and `x-slack-retry-reason` headers; optional "Delayed Events" adds hourly retries for 24h. `x-slack-no-retry: 1` suppresses retries for a given failure.
- Failure limits: >95% failed deliveries within 60 min → subscriptions auto-disabled (email to app owner; manual re-enable). Apps under 1,000 events/hour are exempt. Rate cap: 30,000 events/workspace/app/60 min, then `app_rate_limited` events.

### 2.4 ERPNext / Frappe outbound Webhook DocType

Primary: [Frappe framework webhooks guide](https://docs.frappe.io/framework/user/en/guides/integration/webhooks).

- Configuration per webhook: DocType + doc event + optional condition + request URL + method (default POST) + custom headers; body as form fields or JSON with Jinja templating over `doc`.
- Security: optional **Webhook Secret**; when set, Frappe adds header `X-Frappe-Webhook-Signature` = base64-encoded **HMAC-SHA256 of the payload** with the secret. A `Webhook Request Log` is written per request.
- So "ERPNext fires a HUF App Event" = HUF receives a Frappe-signed webhook. Verification is shared-secret HMAC over the raw body — structurally similar to Slack but a different header/format, and it needs the secret stored on the HUF side. Everything it can send is configured via Jinja, so the envelope can be shaped at the source.

### 2.5 Summary matrix

| System | Push mechanism | Sender auth | Event ID for dedupe | Payload contains data? | Renewal burden |
|---|---|---|---|---|---|
| Gmail | Gmail watch → Pub/Sub push | OIDC JWT (Google-signed) in `Authorization` | Pub/Sub `messageId`; semantic cursor = `historyId` | No (emailAddress + historyId; needs `history.list`) | Re-watch ≥ every 7 days, recommended daily |
| Calendar | Watch channel → HTTPS POST | Optional channel `token` echoed in header | None (`X-Goog-Message-Number` not sequential) | No (headers only; needs API call) | New channel before expiry (~≤1 week); overlap → dupes |
| Slack | Events API POST (or Socket Mode) | HMAC-SHA256 signing secret + timestamp | `event_id` (globally unique) | Yes (full event JSON) | None (but url_verification at setup; auto-disable risk) |
| ERPNext | Frappe Webhook DocType POST | Optional HMAC-SHA256 `X-Frappe-Webhook-Signature` | None by default (can inject `{{ doc.name }}` + event via Jinja) | Yes (Jinja-shaped) | None |

Key design consequence: **only Slack and ERPNext deliver self-contained, verifiable event payloads. Both Google systems deliver thin "something changed" pings that require a follow-up API sync** — so a Gmail/Calendar "App Event" pipeline is really a notification-driven sync loop, not a webhook relay.

---

## Part 3 — Critical evaluation of the proposed design

The proposal: one `Source System` DocType (`webhook_key` as Password, `auth_config` JSON, `watch_state` JSON) + one physical endpoint `source_system_webhook(slug, key)` extending #412's pattern + event envelope `{source, event_id, event_type, occurred_at, payload}` with Redis dedupe (24h) + Virtual Trigger = `Agent Trigger(type='App Event', source_system link, event_name)` + matcher fan-out to `run_agent_sync(channel_id='app_event', external_id=source:event_id)` + `huf_app_events` hook registry + daily watch-renewal scheduler; first consumer Google (Gmail), then Slack, then ERPNext.

### 3.1 What holds

- **Password-typed secret.** Correct and necessary. Current `webhook_key` is Data (plaintext) in both develop's schema and #412. Telegram already shows the `get_password` pattern (`telegram_webhook.py:79-83`).
- **One physical endpoint + fan-out to virtual triggers.** Matches the two working precedents (flow webhook, Telegram) and keeps the guest-facing attack surface to one code path. Reusing the `agent_hooks.py` cache-and-match pattern for the matcher is the obvious right move.
- **Envelope + dedupe.** Genuinely required: Slack retries 3×, Pub/Sub retries unacked messages, Calendar overlap channels double-deliver. 24h Redis dedupe covers all realistic retry windows.
- **Virtual triggers on the existing schema.** `is_virtual`, `source_system`, `app_name`, `event_name` all exist already; no DocType migration needed for the trigger side.
- **`huf_app_events` registry.** Consistent with the proven `huf_tools` hook pattern (`hooks.py:342`, `tool_registry.py`).
- **Watch-renewal scheduler.** Aligned with Google's "call watch daily" recommendation; Frappe `scheduler_events.daily`/`hourly` slots already exist.

### 3.2 What breaks or is underspecified

1. **One slug/key endpoint cannot authenticate all four systems.** Slack needs HMAC over raw body + timestamp window; Pub/Sub needs OIDC JWT validation against Google certs and `aud`/`email` claims; Frappe sends its own HMAC header; Calendar offers only the echoed channel token. A single `key` query param is sufficient for none of the signed systems as the *primary* verification. `auth_config` JSON on Source System is the right container, but the endpoint must branch into **per-system auth adapters** (raw-body HMAC, JWT verify, token compare, shared key) — the design implies one uniform check. Note the ordering constraint: HMAC systems need the raw body before JSON parsing, so the adapter must run before #412-style payload parsing (its `MAX_RAW_BODY_LENGTH` cap is compatible).
2. **Slack's `url_verification` handshake** must be answered synchronously by the endpoint at app-configuration time — a special case the uniform "verify → dedupe → fan-out" pipeline doesn't have. Similarly, **Slack's 3-second ack** and **Pub/Sub retry-until-2xx** both demand the endpoint do almost nothing inline (enqueue and return) — which the design does get right, but it rules out any synchronous `history.list` enrichment before acking.
3. **Google delivers pings, not events.** For Gmail the "payload" is `{emailAddress, historyId}`; the actual "email from VIP" determination requires a `history.list` + message fetch **after** ack, plus a stored per-user `historyId` cursor (this is what `watch_state` JSON is presumably for — make that explicit, it's load-bearing, not incidental). Dropped notifications (Google documents them) mean the cursor can go stale; you need a periodic reconciliation `history.list` per watched user independent of notifications. Calendar is worse: no event id, no body — "dedupe" barely applies; the downstream sync must be **idempotent** instead.
4. **`external_id = source:event_id` is the wrong conversation identity.** Session id resolves to `channel:external_id` (`conversation_manager.py:325-334`), so per-event `external_id` spawns a fresh conversation per event and the agent never accumulates context (e.g. an email thread with a VIP). Identity should be per source-user/mailbox/channel (`gmail:user@example.com`, `slack:T123:C456`), honoring `persist_user_history`; `event_id` belongs to the dedupe layer, not the conversation layer.
5. **Watch renewal failure modes are silent.** Missed renewal → notifications stop with no error on either side (both Google systems). The renewal job must: read `watch_state.expiration`, renew well ahead (e.g. when <48–72h remain, checked hourly rather than only daily), and on renewal failure (revoked refresh token, expired grant) mark the Source System errored + surface it (disabled_reason / notification). Today's credential layer makes this worse: refreshed Google access tokens aren't persisted (`gmail.py` ~37, `credentials.py:4-5` TODO) and there's no consent flow in HUF — the watch APIs need scopes (`gmail.readonly`+ for watch/history) that the externally-provisioned refresh token may not have.
6. **Volume/rate mismatches.** Slack can push up to 30k events/hour/workspace; enqueueing an LLM `run_agent_sync` per matched event on queue `long` will drown the worker. The matcher must filter aggressively *before* enqueue (event_name allowlist, optional condition eval — `Agent Trigger.condition` is currently Doc-Event-only, `agent_trigger.py:15-22`), and Gmail's notification fan-out should be collapsed per user+historyId (multiple notifications between syncs = one sync). Slack's auto-disable at >95% failure/60min turns HUF downtime into a manual re-enable chore.
7. **Who does the agent run as?** #412 settled on "trigger owner" for webhooks. For app events the natural analog is the Source System owner or the connected account's mapped Frappe user — but the proposal doesn't say, and it determines permissions, conversation history (`persist_user_history`), and audit. Specify it.
8. **No Controller validation for App Event.** `AgentTrigger.validate()` (`agent_trigger.py:15-22`) only handles Doc Event and Schedule. App Event triggers need: `event_name` required, source_system resolution, and (for virtuals) guards against user edits — none exists today, and `event_name` lacks even a `depends_on` in the JSON.
9. **Observability gap.** The design has no event log. Every precedent writes something inspectable (Agent Run per dispatch, Webhook Request Log on the Frappe side). A lightweight inbound-event log (source, event_id, matched triggers, enqueue result) is close to mandatory for debugging "why didn't my agent fire" — and gives the dedupe layer a persistent audit trail beyond 24h Redis.

### 3.3 Gaps not addressed by the proposal

- OAuth lifecycle for Google: no consent flow, no scope inventory, unpersisted access tokens. Phase 1 must decide: extend `Integration Settings` + `credentials.py`, or adopt/build a proper Google account DocType.
- Secret rotation and multi-account support (N Gmail users = N watches = N cursor states).
- Backpressure/batching: no mechanism to coalesce bursts (Gmail's 1/sec/user ping during a mailbox import → hundreds of near-identical agent runs).
- Prompt construction for events: reuse #412's explicitly-untrusted payload prompt builder rather than inventing a third one.
- Socket Mode for Slack: avoids the public-endpoint and signing-verification work entirely for self-hosted single-workspace deployments — worth considering as an alternative adapter, at the cost of a persistent worker connection.

---

## Part 4 — Recommendation

### 4.1 Verdict per design element

| Element | Verdict | Notes |
|---|---|---|
| Source System DocType (Password key, auth_config, watch_state) | **Hold (modify)** | Add an explicit `auth_strategy` field (shared_key / hmac_sha256 / google_oidc / slack_signing / calendar_token) so the endpoint branches declaratively instead of heuristically. Keep `watch_state` but treat it as load-bearing (cursor + expiry + last error). |
| One physical endpoint extending #412 | **Modify** | One route, but per-system adapters inside: raw-body capture before parsing, `url_verification` short-circuit, per-strategy verification, enqueue-and-ack. Do not reuse #412's `key`-param check as the universal verifier. |
| Event envelope + 24h Redis dedupe | **Hold (modify)** | Dedupe where a real ID exists (Slack `event_id`, Pub/Sub `messageId`). For Calendar (and Gmail semantics) make the downstream sync idempotent instead of pretending pings are dedupable events. |
| Virtual Trigger = Agent Trigger(App Event) | **Hold** | Schema already supports it; add controller validation (event_name required, virtual-edit guards) and an `event_name` `depends_on`. |
| Matcher fan-out to `run_agent_sync` | **Hold (modify)** | Fix conversation identity: `channel_id='app_event'`, `external_id=<source>:<source-user>` honoring `persist_user_history`; `event_id` stays in the dedupe/log layer. Filter before enqueue; add per-trigger condition support for app events. |
| `huf_app_events` hook registry | **Hold** | Follows the `huf_tools` precedent. |
| Daily watch-renewal scheduler | **Hold (modify)** | Hourly check renewing anything expiring within 48–72h; explicit error state + alerting on renewal failure; reconciliation `history.list` fallback per watched user. |
| Order: Google first, Slack second, ERPNext third | **Modify** | **Slack is the cheapest true end-to-end proof** (self-contained signed payloads, real `event_id`, no renewal machinery, no OAuth scopes beyond what HUF already consumes via bot token). Google is the highest-value but also the heaviest (Pub/Sub infra, OIDC, watch renewal, cursor sync, unpersisted tokens). Recommend: prove the bus with Slack or ERPNext, then do Google as the first "sync-driven" system. If Google-first is a hard product requirement, scope it to Gmail only. |

### 4.2 Phase-1 spike outline (Google / Gmail), ~1–2 weeks

1. **Infra:** one GCP project, Pub/Sub topic `huf-gmail`, push subscription with OIDC auth (service account + `serviceAccountTokenCreator` grant), publish rights for `gmail-api-push@system.gserviceaccount.com`. Document the exact `gcloud` commands in the spike PR.
2. **Source System DocType (minimal):** name, `auth_strategy`, Password key, `auth_config` (GCP project, topic, expected `aud`, push-auth SA email), `watch_state` (`historyId`, `watch_expiration`, `last_renewal`, `last_error`).
3. **Endpoint:** `source_system_webhook(slug)` — verify OIDC JWT (signature + `aud` + `email`), ack immediately, enqueue `process_app_event`. Raw-body cap and untrusted-prompt builder copied from #412.
4. **Worker:** decode `message.data` → `{emailAddress, historyId}`; dedupe on `messageId` (24h Redis); per-user cursor: `history.list(startHistoryId=stored)`, fetch new messages, evaluate matcher (Virtual Triggers where `source_system` + `event_name` match, e.g. `gmail.message_received`); store new historyId even on zero matches.
5. **Dispatch:** `run_agent_sync(channel_id='app_event', external_id=f'gmail:{emailAddress}')`, run as Source System owner, queue `long`, UUID job ids (existing patterns).
6. **Renewal:** hourly scheduler — re-`watch` when `watch_expiration < now+48h`; on failure set error state + log. Register initial watch from the Source System form (button), storing response `historyId`/`expiration`.
7. **Demo:** "email from VIP → agent drafts reply" with one Gmail account, one Virtual Trigger. Success criteria: end-to-end latency < 60s, no duplicate agent runs across Pub/Sub retries, 7-day soak with unattended renewal.
8. **Explicitly out of scope for the spike:** Calendar, multi-account UI, Socket Mode, Slack/ERPNext adapters, event-log DocType (use Error Log + Agent Run in the interim).

### 4.3 Open questions for the owner

1. **Google OAuth home:** extend `Integration Settings`/`credentials.py` (persist refreshed access tokens, add scope inventory), or introduce a proper "Google Account" DocType with an in-app consent flow? Watch APIs need scopes current refresh tokens may not have — who provisions them?
2. **Ordering:** accept Slack/ERPNext-first as the bus-proving phase, or is Gmail-first a fixed product commitment?
3. **Conversation identity:** confirm per-source-user conversations (`gmail:user@x.com`) over per-event ones; should `persist_user_history=0` app-event agents share one conversation per source system?
4. **Run-as identity:** Source System owner, trigger owner, or a mapped Frappe user per connected external account?
5. **Event log:** new `App Event Log` DocType (auditable, queryable) or reuse Error Log/Agent Run only?
6. **Multi-tenancy:** how many watched Gmail users/workspaces must phase 2 support, and is there a per-site or per-customer GCP project model?
7. **Slack transport:** HTTP endpoint with signing-secret verification, or Socket Mode (no public endpoint) for self-hosted deployments?
8. **Backpressure policy:** cap agent runs per source per minute? Coalesce Gmail syncs when notifications burst?

---

## Appendix — Key references

Code (this branch unless noted):

- `huf/huf/doctype/agent_trigger/agent_trigger.json:55-59,99-121,146-156` — trigger_type options; webhook/app-event/source fields.
- `huf/huf/doctype/agent_trigger/agent_trigger.py:15-34` — validate() covers Doc Event + Schedule only.
- `huf/ai/agent_hooks.py:12-77,80-139,141-299` — Doc Event cache, enqueue, dispatch, conversation identity.
- `huf/ai/agent_scheduler.py:6-56` + `huf/hooks.py:175-205,227-244,342` — scheduler/doc_events/huf_tools wiring.
- `huf/ai/flow_api.py:332-418` — flow webhook auth pattern.
- `huf/ai/tools/telegram_webhook.py:53-179` — Telegram secret-header pattern.
- `huf/ai/tools/credentials.py:21-74`, `gmail.py:9-52`, `google_meet.py:11-24`, `google_calendar.py:11-28` — credential resolution, refresh-token flow.
- `huf/ai/agent_integration.py:631-688`, `huf/ai/conversation_manager.py:325-394` — run_agent_sync signature, session-id resolution.
- `huf/ai/agent_trigger_api.py` on `origin/task/CD-B-02-webhook-manual` (unmerged, `f739b58`) — Webhook/Manual endpoints (draft PR #412).

External (primary):

- Gmail push: https://developers.google.com/workspace/gmail/api/guides/push
- Pub/Sub push auth: https://cloud.google.com/pubsub/docs/authenticate-push-subscriptions
- Calendar push: https://developers.google.com/workspace/calendar/api/guides/push
- Slack Events API: https://docs.slack.dev/apis/events-api/
- Slack request verification: https://docs.slack.dev/authentication/verifying-requests-from-slack/
- Frappe webhooks: https://docs.frappe.io/framework/user/en/guides/integration/webhooks
