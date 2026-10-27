# WhatsApp Broadcast

A WhatsApp Broadcast sends one approved template message to a bounded, pre-approved list of recipients through the Meta WhatsApp Cloud API. It is an automation tool. It is not a campaign platform, a CRM, or an inbox: there is no audience builder, no scheduling calendar, no A/B testing, and no replies are handled by the broadcast (replies arrive through the normal inbound flow).

Status of this document: it describes the design in the WhatsApp Broadcast track contract. Parts that depend on Meta behaviour that could not be confirmed from the official pages are marked **unverified**. See the live verification plan in [broadcast-live-verification.md](broadcast-live-verification.md).

## 1. Scope

In scope:

- One template per broadcast, one `POST /<PHONE_NUMBER_ID>/messages` request per recipient (`type: template`). Meta offers no multi-recipient broadcast endpoint.
- Per-recipient parameters, merged over the broadcast defaults.
- Recipients from pasted numbers or a CSV file.
- Preview (recipient count, skipped rows, template status, 24-hour budget, estimated cost) and a typed-count confirmation before start.
- Pause, resume, cancel, and a gateway-wide kill switch.
- Status tracking from Meta status webhooks (`sent`, `delivered`, `read`, `failed`).

Out of scope for v1:

- The Marketing Messages API (`/marketing_messages`). Marketing templates still go through `/messages` in v1. This path is a later optional package and is required before 2027-04-13 for marketing sends from accounts created after that date (see section 11).
- Retrying failed rows. There is no action to resend rows that ended `failed`, `skipped`, or `unknown`.
- Sending to WhatsApp groups (not supported in Huf, see the [WhatsApp README](README.md)).
- Free-form messages. Broadcasts send templates only, so the 24-hour conversation window does not apply.

## 2. Consent and opt-in

A broadcast may only reach people who have opted in to receive messages from the business.

- Before start, an operator must attest the opt-in for the list. The attestation records the opt-in source (`consent_source`), the user who attested (`consent_attested_by`), and the time (`consent_attested_at`). Start is refused until `consent_attested` is set.
- Each recipient row can carry its own `consent_source` and `consent_at`. These are stored for audit. They do not replace the attestation.
- Before a recipient is queued, the broadcast checks Huf's opt-out data: a STOP from the contact (`is_opted_out`, see the [runbook](../gateways/whatsapp-runbook.md#6-stop--start-opt-out)) and a marketing stop from Meta's `user_preferences` webhook (`is_marketing_allowed`). A contact that matches is recorded as `skipped` with a reason and is never sent to.
- Before each send, the same opt-out check runs again. A contact that opted out after the list was built is marked `skipped`.
- For marketing templates, US `+1` numbers are filtered out during preview because WhatsApp does not currently deliver marketing templates to them. The filter is counted in the preview.
- Numbers are normalised to digits-only E.164. Invalid numbers are reported as `invalid` and not added. Duplicates are removed.

## 3. Recipient state machine

Each recipient is one `WhatsApp Broadcast Recipient` row. Its `status` field holds the state.

```
queued ──claim──> sending ──> sent ──> delivered ──> read
  ^  |               │         │
  │  │               ├──> failed            (failed never overwrites delivered or read)
  │  │               ├──> deferred ──(next_attempt_at)──> sending
  │  │               └──> unknown          (never resent automatically)
  │  └──> skipped                          (opt-out, consent, cap, or cancel)
  └──────── deferred rows wait here until due
```

Rules:

- **Claim.** A worker moves a row to `sending` with a conditional update (`WHERE status IN ('queued','deferred')`) and commits before it calls Meta. If the update matches no row, another worker owns it and the worker does nothing.
- **Rank.** Status only moves forward. Ranks: `queued` and `deferred` 0, `sending` 1, `sent` and `unknown` 2, `delivered` 3, `read` 4. A webhook for an earlier state never moves a row back.
- **Unknown.** If the process crashes or times out after the request was sent but before the message id was stored, the row becomes `unknown`. Rows left in `sending` for more than 10 minutes are moved to `unknown` by the periodic recovery job. `unknown` is never sent again automatically, because the message may already have been delivered.
- **Failed.** A row becomes `failed` for a permanent Meta error, or after 5 failed attempts on a retryable error.
- **Skipped.** Opt-out, consent change, the per-broadcast cap, or cancellation. The reason is stored in `skip_reason`.
- **Wamid.** On a successful send, the message id (`wamid`), `message_status` (`accepted` or `held_for_quality_assessment`), and `sent_at` are stored. Status webhooks are matched to a row by `wamid`, or by `opaque_ref` (the recipient row name) when the `wamid` is not found.
- **Counters.** The counts on the broadcast (`queued`, `sending`, `sent`, `delivered`, `read`, `failed`, `deferred`, `unknown`, `skipped`) are recomputed from the recipient rows. The rows are the source of truth.

No WhatsApp Send Key rows are written by a broadcast. Send keys expire after 15 minutes or 24 hours and count toward the agent per-day cap, so the broadcast uses its own state machine as its duplicate guard.

## 4. Broadcast lifecycle

Broadcast `status`: `Draft`, `Queued`, `Running`, `Paused`, `Completed`, `Cancelled`, `Failed`.

| Action | Allowed from | Result |
|---|---|---|
| Create | none | `Draft`. Template, defaults, caps, and gateway are set. |
| Add recipients | `Draft` | Rows are added as `queued` or `skipped`. |
| Attest consent | `Draft` | Records the opt-in attestation. |
| Preview | any | Read only. Returns counts, limits, warnings, blocking reasons, and cost. |
| Start | `Draft`, `Paused` | Checks the rules below, sets `Running`, records `started_by` and `started_at`, and starts the runner. |
| Pause | `Running` | `Paused` with a reason. Queued rows wait. |
| Resume | `Paused` | `Running` again. Checks run again. |
| Cancel | `Draft`, `Running`, `Paused` | `Cancelled`. Queued rows become `skipped` with reason `cancelled`. Rows already sent are not changed. |
| Complete | `Running` | Set when no queued or deferred rows remain. `finished_at` is set. |

Start is refused unless all of these hold:

- the template is `APPROVED` at start time (checked again, not only at draft time);
- consent is attested;
- the preview has no blocking reasons;
- the typed confirmation equals the number of queued recipients (`confirm_count`);
- no other broadcast is `Running` on the same gateway (one active broadcast per gateway).

The runner sends as the user who started the broadcast. Write permission on the gateway is checked at start and again on each tick. If that permission is removed, the broadcast pauses.

## 5. Limits, pacing, and pause rules

### Limits

- **Per-broadcast cap.** `max_recipients` on the broadcast. Rows beyond the cap are not sent. The cap is enforced by the sender, not only by the preview.
- **Portfolio budget.** Meta limits the number of unique users a business portfolio can message outside a service window in a rolling 24 hours (tiers 250, 2,000, 10,000, 100,000, unlimited). The preview reads the current tier from `whatsapp_business_manager_messaging_limit`. The remaining budget is the tier minus unique recipients already started by any broadcast on the gateway in the last 24 hours. If the tier cannot be read, the value is unknown and the preview warns.
- **Per-user marketing limit.** Meta can withhold marketing templates to a user who receives too many. This is handled per recipient (error 131049, section 6).

### Pacing

- `mps` (messages per second) on the broadcast sets the send rate. It is capped by the phone number's throughput (default 80 mps, see [Meta throughput](#14-meta-references)) and by the throughput reported by Meta when it can be read.
- The first batch is a ramp of 20 messages. Later batches grow.
- Sends are paced in chunks. The runner re-queues itself after each chunk, so a restart resumes from the rows still `queued`.
- **Held ratio.** When more than 30% of recent sends return `message_status = held_for_quality_assessment`, the runner slows down. Held messages are a Meta signal that the template is under quality assessment.

### Pause signals

The runner pauses the broadcast (with the reason stored in `pause_reason`) when any of these happens:

| Signal | Source | Action |
|---|---|---|
| Error 132015 | Send response or status | Pause. The template was paused or dropped by template pacing. |
| Error 135000 | Status | Pause. Portfolio pacing dropped held messages. |
| Template paused, rejected, or disabled | Template webhook (`message_template_status_update`) | Pause for that template. |
| Gateway write permission removed | Each tick | Pause. |
| Gateway kill switch | `pause_all_broadcasts(gateway)` | Pause every running broadcast on the gateway. |
| Gateway disconnected | Connection state | Refused at send time, see the [runbook](../gateways/whatsapp-runbook.md#3-health-states). |

A paused broadcast does not resend anything. Resume is a manual action.

## 6. Error handling

Classification uses `whatsapp_errors` (`huf/ai/gateway_adapters/whatsapp_errors.py`). Rows that get no response, or an ambiguous network error after the request was sent, go to `unknown`, not to a retry.

| Code | Meaning | Row outcome | Broadcast |
|---|---|---|---|
| 130429 | Throughput limit | `deferred` with backoff, `attempts + 1` | Continues, slower |
| 131056 | Pair limit (too many messages to one user) | `deferred` with per-recipient backoff | Continues |
| 131057 | Number unavailable during throughput upgrade | `deferred` with a short wait | Continues |
| 5xx | Meta server error | `deferred` with backoff | Continues |
| 131049 | Withheld for ecosystem health (per-user marketing limit) | `deferred`, next attempt at least 24 hours later | Continues |
| 131050 | Recipient opted out of marketing | `failed`; a marketing stop is recorded for the contact | Continues |
| 131026 | Undeliverable (no WhatsApp, old app) | `failed` | Continues |
| 131048 | Sending restricted on the number | `failed` | Continues. Check quality in WhatsApp Manager. |
| 132012 | Template parameter mismatch | `failed` | Continues. Fix the payload. |
| 132016 | Template permanently disabled | `failed` | Pauses |
| 132015 | Template paused or dropped by pacing | row not sent | Pauses |
| 135000 | Held message dropped under portfolio pacing | `failed` | Pauses |
| 131042 | Payment or billing problem | `failed` | Pauses |
| 131062 | BSUID recipient not supported for this message | `failed` | Continues |
| Other permanent | Not retryable | `failed` | Continues |
| Timeout or ambiguous after request | Unknown whether Meta accepted it | `unknown` | Continues. Never resent automatically. |

Retryable rows are retried up to 5 attempts, then `failed`. Backoff is taken from `whatsapp_errors.backoff_seconds`.

Status webhooks for a broadcast row:

- `sent`, `delivered`, `read` move the row forward (monotonic).
- `failed` moves a row to `failed` with the error code and message stored, unless it is already `delivered` or `read`.
- A repeated `(wamid, status)` pair is ignored.
- A failed webhook handler never breaks webhook ingest.
- A user-stop error from a status (131050) also marks that contact's queued and deferred rows in running broadcasts as `skipped` with reason `opted_out`.

## 7. Costs

Meta charges per delivered marketing message, by recipient country calling code. Utility and authentication rates have volume tiers; marketing does not.

- The preview shows an estimate in USD built from a rate card file, `huf/ai/whatsapp/broadcast_rates.json`. The file records its source URL and the date it was taken.
- A country missing from the rate card has `rate: null`. The estimated total becomes unknown and the preview warns.
- The estimate is not an invoice. Meta's pricing page and the WhatsApp Manager billing view are the source of truth.
- Start requires the operator to type the recipient count. The count must match the queued recipients exactly. This is a guard against starting a list that was changed after the preview.

## 8. API reference

All endpoints are whitelisted methods in `huf/ai/whatsapp/management.py`. Each one is guarded by the bridge guard and by gateway write permission (`_gateway_write_allowed`). Every mutating call writes an audit log entry (`huf.whatsapp.broadcast` logger) and a comment on the broadcast.

| Method | Purpose | Key arguments |
|---|---|---|
| `create_broadcast` | Create a draft | `gateway`, `template`, `title`, `language_code`, `body_params`, `header_params`, `button_params`, `consent_source`, `max_recipients`, `mps` |
| `add_broadcast_recipients` | Add recipients from a list or CSV | `broadcast`, `recipients`, `csv_text` |
| `attest_broadcast_consent` | Record the opt-in attestation | `broadcast`, `consent_source` |
| `preview_broadcast` | Counts, limits, warnings, blocking reasons, cost | `broadcast` |
| `start_broadcast` | Start the run | `broadcast`, `confirm_count` |
| `pause_broadcast` | Pause | `broadcast` |
| `resume_broadcast` | Resume | `broadcast` |
| `cancel_broadcast` | Cancel | `broadcast` |
| `pause_all_broadcasts` | Kill switch for a gateway | `gateway` |
| `list_broadcasts` | List | `gateway`, `status`, `limit`, `offset` |
| `get_broadcast` | Detail with counts | `broadcast` |
| `list_broadcast_recipients` | Recipient rows | `broadcast`, `status`, `limit`, `offset` |

There is no endpoint to retry failed rows. To send again to those contacts, create a new broadcast with a new list. Rows already `sent`, `delivered`, or `read` are not sent again by any action.

The Meta endpoints used are:

- `POST /<PHONE_NUMBER_ID>/messages` (template send, per recipient), with `biz_opaque_callback_data` set to the recipient row name. Meta's size limit and placement for this field are unverified; the row name is well under 256 characters.
- `GET /<PHONE_NUMBER_ID>?fields=whatsapp_business_manager_messaging_limit,quality_rating,throughput` (limits, read-only, cached for 10 minutes; a failure leaves the values unknown and does not raise).
- Template status read before start and in preview.

Webhook fields used: `messages` (statuses), `message_template_status_update`, `message_template_quality_update`, `user_preferences`.

## 9. Operational runbook

Full gateway runbook: [whatsapp-runbook.md](../gateways/whatsapp-runbook.md#10-broadcasts).

Typical sequence:

1. Confirm the gateway health is `healthy` or `degraded` with no blocking reasons.
2. Check the template in WhatsApp Manager: `APPROVED`, and note its category.
3. Create the draft, add recipients, attest consent with a source.
4. Preview. Read the warnings, the remaining 24-hour budget, the skipped reasons, and the cost estimate.
5. Start with the typed count.
6. Watch the counts. Pause if `failed` or `deferred` rises quickly, or if held ratio rises.
7. Check the audit comments on the broadcast after the run.

Kill switch: `pause_all_broadcasts(gateway)` pauses every running broadcast on the gateway. Use it first when a template or number is in trouble, then investigate.

## 10. Known limits

- **No retry of failed rows.** `failed`, `skipped`, and `deferred` rows that never sent are not resent by a later action. Create a new broadcast for those contacts if they should receive the message.
- **Unknown rows are never resent automatically.** An `unknown` row may have been delivered. Check the recipient in the business inbox or the WhatsApp Manager message log before deciding anything.
- **No automatic 24-hour retry for 131049 beyond one deferral.** A deferred row becomes due at least 24 hours later and is then sent once more under the normal retry limit.
- **Portfolio budget is a read.** The tier comes from a Meta read that can fail. When it is unknown, the preview warns and the start guard relies on the per-broadcast cap.
- **Held messages are not a delivery signal.** `held_for_quality_assessment` means Meta accepted the request but is holding it. Its final result comes from the status webhooks.
- **Pair limit numbers are unverified.** The 1-message-per-6-seconds figure comes from an older Meta page. Treat 131056 as per-recipient backoff only.
- **Marketing Messages API not used.** Custom TTL and marketing product-policy options are not available on the `/messages` path.
- **Rate card may be stale.** The cost estimate is only as current as `broadcast_rates.json`.
- **No inbox.** Replies are handled by the normal inbound flow, not by the broadcast.

## 11. Meta changes that affect this design

- Marketing messages on the Cloud API are scheduled to stop on 2027-10-13. New accounts are blocked from marketing on the Cloud API from 2027-04-13. The Marketing Messages API is required for marketing sends after those dates. This is tracked as the optional package WP-10.
- Template TTL is set on the template, not on the send payload. The marketing TTL option requires the Marketing Messages API.
- Business-scoped user IDs (BSUIDs) may appear instead of phone numbers in webhooks. Recipients are keyed by phone number and by BSUID where Meta provides one.

## 12. Open questions

- Exact placement and size limit of `biz_opaque_callback_data` in the send body (search snippet says 512 characters; the design uses 256 for safety).
- Whether the per-user marketing limit applies identically to the Marketing Messages API.
- Current US `+1` marketing block effective date.
- Downgrade rules for messaging tiers.
- Current pair-limit numbers.

These are verified against the raw Meta pages before the live verification run. See `research/META_BROADCAST_API.md` in the track.

## 13. Glossary

- **Template**: a Meta-approved message with placeholders. Must be `APPROVED` to send.
- **Held for quality assessment**: a send accepted by Meta but held while the template is assessed.
- **Opt-in attestation**: the operator's record that the recipients opted in to the business's messages, and how.
- **Wamid**: WhatsApp message id returned by the send call and echoed in status webhooks.

## 14. Meta references

- Send messages: <https://developers.facebook.com/documentation/business-messaging/whatsapp/messages/send-messages>
- Messaging limits: <https://developers.facebook.com/documentation/business-messaging/whatsapp/messaging-limits>
- Throughput: <https://developers.facebook.com/documentation/business-messaging/whatsapp/throughput>
- Template pacing and portfolio pacing: <https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/template-pacing>
- Status webhook: <https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/reference/messages/status>
- Pricing: <https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing>
- Error codes: <https://developers.facebook.com/docs/whatsapp/cloud-api/support/error-codes>

## Marketing Messages API (send_via)

A broadcast has a `send_via` field: `messages` (default, `POST /{phone-number-id}/messages`) or `marketing_messages` (`POST /{phone-number-id}/marketing_messages`, the Meta Marketing Messages API, "MM API"). Payload, components and response shape (`messages[0].id`, `message_status`) are the same, so the rest of the broadcast pipeline is unchanged.

When to use it:
- Marketing templates only. A `marketing_messages` broadcast with a non-MARKETING template is refused (`mm_requires_marketing_template`, at create and again per recipient as `failed`).
- Meta states the Cloud API stops supporting marketing messages on 2027-10-13 and that new accounts are blocked from Cloud API marketing from 2027-04-13 (per the track research; the send page itself does not state these dates, so re-verify). Accounts onboarded after the April date must use `marketing_messages`.
- It also is the only path with a custom marketing template TTL (12h to 30d; Cloud API marketing is fixed at 30 days). TTL is set on the template, not per send.

Requirements and caveats:
- The business must have completed MM API onboarding (terms accepted, Pixel or Conversions API for measurement). Huf sends the default `product_policy` (`CLOUD_API_FALLBACK`): if onboarding is incomplete Meta falls back to the Cloud API `/messages` behaviour. Huf does not send `product_policy: STRICT` or `message_activity_sharing` (account default applies).
- Status webhooks may report `marketing_lite` (sent via MM API) or `marketing` (fell back).
- It is not documented whether the per-user marketing limit (131049) behaves identically on MM API. **Unverified**; the existing 131049 deferral applies unchanged.
- `create_broadcast(..., send_via="marketing_messages")` sets it; it is not exposed in the UI yet.
