# WhatsApp Gateway Operator Runbook

Behaviour is taken from code; file references name the source of truth. Setup guide:
`docs/WHATSAPP_INTEGRATION_SETUP.md`. Never put credentials in this document, chat or logs.

## 1. Access token expiry and rotation

- Meta error 190 means the token is invalid or expired (`huf/ai/gateway_adapters/whatsapp_errors.py`).
- Rotate the token in BOTH places: the gateway's integration credential `access_token` (used for agent replies) and the linked WhatsApp Account `token` (used by the bridge: confirmations, templates, management). If only one is refreshed, some sends work and others fail with 131005/190.
- Token check: `check_token(gateway_name, force)` in `huf/ai/whatsapp/management.py` (POST, whitelisted).
  It calls Meta `debug_token` and `subscribed_apps` (`huf/ai/whatsapp/token_check.py`). The result
  is cached for 600 s and live checks are limited to one per 10 s. `force` bypasses the cache.
- Health reads only the cached result. A rejected token raises `access_token_invalid` (error),
  blocks the `credentials` step and sets next step "Replace access token".
- Rotation:
  1. Generate a new system user token in Meta Business settings.
  2. Replace the token in the gateway Settings (`#credentials`).
  3. Run the token check with `force` and confirm `access_token_invalid` is gone.
  4. Confirm the next inbound message produces a Gateway Event with a successful reply.

## 2. Webhook and subscription check

- GET verification (`hub.mode`, verify token) is handled in `huf/ai/gateway_adapters/whatsapp.py`.
  A pass sets `Gateway.last_verify_ok_at`.
- A failed POST signature or GET verify token sets `last_signature_failure_at`, which raises
  `signature_failed` (error) for 24 hours or until the next valid event. Check the App Secret.
- Gateway Events are created only for inbound messages, so the `messages` field must be subscribed.
  `no_events_yet` (warning) means Meta has not sent anything: check the callback URL and subscription.
- `webhook` and `subscribed` checklist steps are inferred from Huf data (no Meta read API).
- `subscribed_apps` and `debug_token` response shapes are marked UNVERIFIED in `whatsapp/token_check.py`.
  If the app entry is missing, the check reports only that some app is subscribed.

## 3. Health states

**Connection state** (`Gateway.connection_state`, set from Meta `account_update` webhooks in
`huf/ai/whatsapp/account_events.py`; no Gateway Event is created, a Gateway comment is the audit):

| State | Set by | Effect |
|---|---|---|
| Connected | `ACCOUNT_RECONNECTED`; `DISABLED_UPDATE` with ban `REINSTATE` | Normal sends |
| Degraded | `ACCOUNT_RESTRICTION`, `ACCOUNT_VIOLATION`; ban `SCHEDULE_FOR_DISABLE` | Sends allowed; warning `gateway_degraded` |
| Disconnected | `PARTNER_REMOVED`, `ACCOUNT_OFFBOARDED`, `ACCOUNT_DELETED`; ban `DISABLE` | Sends refused (`gateway_disconnected`) |

Any enabled gateway on a Disconnected number refuses sends (`send_refusal`). Only a later Meta event changes the state.

**Health** (`evaluate` in `huf/ai/whatsapp/health.py`, a pure function over DB facts, no network):

| Health | Meaning |
|---|---|
| disabled | Gateway disabled |
| not_set_up | Nothing configured, or no events yet and no blocking error |
| blocked | Any error reason: missing token, verify token or App Secret; invalid token; account mismatch; signature failure; Run-as user not authorized; Disconnected |
| degraded | Warnings only: delivery failures, agent failures, recent error, fallback template rejected/paused/disabled, Degraded connection |
| healthy | No reasons |

Counts cover 24 hours. Agent failures are `Failed` events whose error starts with `provider_<kind>:`
or `agent_run_failed:`. Other `Failed` events, or `reply_status` failed, count as delivery failures.

## 4. Dead letters and retry

- A deterministic ingest failure is kept as a `Failed` Gateway Event whose `error_message` starts
  with `dead_letter:` (`store_ingest_dead_letter` in `huf/ai/gateway_service.py`). The redacted raw
  payload and ingest context are kept, so nothing is dropped.
- Created by the webhook (`_dead_letter` in `huf/ai/gateway_webhook.py`) and by the reaper when an
  orphaned `Received` event fails to replay.
- Replay: `retry_gateway_event(name)` (POST, whitelisted, `huf/ai/gateway_service.py`).
  - Requires Gateway administrator permission.
  - Only `Failed` rows with the `dead_letter:` prefix are replayed. Other failed events are refused.
  - Idempotent: a non-failed row returns `replayed: false` without change.
  - On failure the savepoint rolls back and the row returns to `Failed` with its previous error.

## 5. Reaper recovery

Cron `*/10 * * * *` runs `reap_stuck_gateway_events` (`huf/hooks.py`). At most 50 events per sweep.

| Condition | Threshold (since `modified`) | Action |
|---|---|---|
| `Running`, not reply-retrying | 15 min | Failed ("Stuck in Running"); sender notice flagged |
| `Queued` | 10 min | Re-enqueue `process_gateway_event` |
| `Received` | 5 min | Replay ingest; failure becomes a dead letter |
| `Running` + `reply_status = retrying` | 10 min | Re-enqueue reply retry from the Agent Run; if the unsent part cannot be rebuilt, Failed |

- Attempts are stored in `recovery_attempts` (max 3); `retry_deadline` is 60 min after the first. Exhausting either ends the event Failed and notifies the sender.

## 6. STOP / START opt-out

Handled at ingest by `_handle_consent_event` (`huf/ai/gateway_service.py`). WhatsApp only.

- Defaults. STOP: `STOP`, `UNSUBSCRIBE`, `CANCEL`, `END`, `QUIT`. START: `START`, `UNSTOP`, `SUBSCRIBE`.
  The gateway can set its own keyword lists and opt-out reply text.
- STOP from an admitted sender records the opt-out, sends the confirmation and starts no agent run.
- START from an opted-out sender records the opt-in, sends the resubscribe confirmation and starts no agent run.
- Other messages from an opted-out sender are rejected ("Sender has opted out").
- STOP or START from a sender with no access entry is ignored, with no row and no reply.
- Outbound sends check `is_opted_out`. The opt-out confirmation is exempt for that one send.
- Meta `user_preferences` marketing stop/resume is stored as `Gateway Consent` rows
  (`whatsapp/account_events.py`); `is_marketing_allowed` returns False when the latest value is `stop`.
  That payload shape is marked UNVERIFIED in the code.

## 7. 24-hour window and fallback template

- Window: 24 hours (`WINDOW_HOURS`, `huf/ai/gateway_adapters/whatsapp_bridge.py`) from the sender's last
  verified inbound Gateway Event, capped at `received_at` so redelivered webhooks cannot reopen it.
  Record-only kinds (edit, revoke, system, unknown) and reactions do not count.
- Free-form send with the window closed:
  - Fallback template configured and `APPROVED`: the template is sent, the agent reply is suppressed,
    and the event note reads "Fallback template sent; agent reply suppressed (24h window closed)".
  - Template known but not `APPROVED`: nothing is sent; the event fails with the template status.
  - No fallback template: `WhatsAppWindowClosed` is raised and the event fails. It is not retried.
- Meta error 131047 on the first part of a reply also triggers the fallback when one is configured.
- Health raises `fallback_template_unavailable` (warning) when Meta marks the template REJECTED,
  PAUSED or DISABLED. Check it in WhatsApp Manager.
- Parameters: `fallback_template_params` if set, else each body variable gets the contact name or "there".

## 8. Voice note replies

Gateway field **Voice note replies** (`voice_reply_mode`): `Off` (default), `Voice only` or `Text and voice`. It applies only when the customer's message was a voice note (audio with `voice: true`); anything else is answered with text as usual.

- Needs `ffmpeg` on the server (converts the speech to Ogg/Opus mono). Install it on every worker host (`apt install ffmpeg`); it must include the `libopus` encoder (`ffmpeg -encoders | grep libopus`).
- To check: the gateway health shows the warning `voice_reply_ffmpeg_missing` ("ffmpeg is missing, so replies go out as text") when voice replies are on and this host lacks ffmpeg or libopus. Saving the gateway shows the same warning. The check runs on the site host, so also verify on each worker host.
- The speech comes from the agent's own TTS model and voice (Agent `tts_model` / `tts_voice`) using that model's provider key.
- Replies longer than 1500 characters (markdown removed) are sent as text only.
- The usual gates apply: STOP opt-out, the 24-hour window (closed window: the text fallback path, including the fallback template), BSUID refusal.
- `Voice only`: one voice note replaces the text. `Text and voice`: the text goes first, then the voice note (skipped if the text is still being retried).
- Any failure (ffmpeg missing, no TTS model, provider error, send refused) is logged as a warning ("WhatsApp voice reply: ...") and the reply is sent as text. The reply is never lost.
- A replayed or retried event never sends a second voice note.

## 9. Triage order

1. Read the gateway health reasons and next step.
2. Run the token check with `force` if credentials are involved.
3. Check `connection_state` and its reason.
4. Review Failed events; replay dead letters with `retry_gateway_event` only after the cause is fixed.
5. If events sit in Queued, Received or Running, confirm the reaper cron is running.

## 10. Broadcasts

Full design and API: [WhatsApp Broadcast](../whatsapp/BROADCAST.md). Management methods are in `huf/ai/whatsapp/management.py`.

- A broadcast sends one approved template to a bounded list through `POST /<PHONE_NUMBER_ID>/messages`, one request per recipient. It is automation only: no inbox, no scheduling.
- One broadcast can run per gateway at a time. Start needs an `APPROVED` template, attested opt-in consent, no blocking preview reasons, and the typed recipient count.
- Recipient states: `queued`, `sending`, `sent`, `delivered`, `read`, `failed`, `deferred`, `unknown`, `skipped`. A row in `sending` for more than 10 minutes becomes `unknown` (recovery job, `*/5 * * * *`).
- `unknown` rows are never resent automatically. Check them in WhatsApp Manager before anything else.
- Failed rows are not retried by any action. To reach the same contacts again, create a new broadcast.
- The runner pauses on 132015, 135000, a template paused, rejected or disabled, or a removed gateway write permission. Resume is manual.
- Kill switch: `pause_all_broadcasts(gateway)` pauses every running broadcast on the gateway. Use it first when a template or number is in trouble.
- Check the messaging limit (`whatsapp_business_manager_messaging_limit`) in the preview. If it is unknown, the preview warns and the per-broadcast cap is the only ceiling.
- Costs in the preview come from `huf/ai/whatsapp/broadcast_rates.json`. Treat them as an estimate and check Meta billing.
- Live verification is described in [broadcast-live-verification.md](../whatsapp/broadcast-live-verification.md). Run it only against allow-listed test recipients.
