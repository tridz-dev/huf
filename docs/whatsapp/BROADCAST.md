# WhatsApp Broadcast

A WhatsApp Broadcast sends one approved template to a bounded, pre-approved list of recipients through the Meta WhatsApp Cloud API. It is an automation tool. It is not a campaign platform, a CRM, or an inbox: there is no audience builder, no scheduling, no A/B testing, and replies are not handled by the broadcast (they arrive through the normal inbound flow).

This document describes the code as it is. Statements that depend on Meta behaviour that was not confirmed are listed in [section 11](#11-unverified-meta-facts). The live check plan is in [broadcast-live-verification.md](broadcast-live-verification.md). The operator summary is in the [gateway runbook](../gateways/whatsapp-runbook.md#10-broadcasts).

Code: `huf/ai/whatsapp/broadcast_recipients.py` (intake), `broadcast_send.py` (one recipient), `broadcast_runner.py` (lifecycle and pacing), `broadcast_status.py` (Meta statuses and stops), `broadcast_limits.py` (limit and preview), `broadcast_cost.py` (estimate), `management.py` (API), doctypes `WhatsApp Broadcast` and `WhatsApp Broadcast Recipient`.

## 1. Scope

In scope:

- One template per broadcast. One request per recipient (`type: template`). Meta offers no multi-recipient send.
- Per-recipient parameters, merged over the broadcast defaults per part (`body`, `header`, `button`).
- Recipients from a list of numbers or a CSV text.
- Preview and a typed-count confirmation before start.
- Pause, resume, cancel, and a gateway-wide kill switch.
- Delivery tracking from Meta status webhooks.
- Two send paths, chosen by `send_via`: `messages` (`POST /<PHONE_NUMBER_ID>/messages`, default) and `marketing_messages` (`POST /<PHONE_NUMBER_ID>/marketing_messages`, MARKETING templates only; section 10).

Not implemented:

- Retry of failed rows. There is no endpoint (`retry_failed_broadcast_recipients` does not exist, by design; section 7).
- Scheduling a start time.
- Groups and free-form messages. Broadcasts send templates only.
- Cost in the preview while no rates are filled in (section 8).

## 2. Consent and recipient intake

A broadcast may only reach people who opted in.

- Before start an operator must attest the opt-in with `attest_broadcast_consent`. It stores `consent_source` (required, non-empty), `consent_attested_by`, `consent_attested_at`, `consent_attested`. Start is refused until it is set. Attestation is allowed in `Draft` and `Paused`. `add_broadcast_recipients` (Draft only) resets the attestation (`consent_attested` 0, by/at/source cleared), so the operator must attest again after every change to the list.
- Writes to a Broadcast through generic REST, the desk form or `doc.save` are rejected unless they go through the broadcast API. Guarded fields: the consent fields, `gateway`, `template`, `whatsapp_account`, `status`, `started_by`, `started_at`, `finished_at`, `pause_reason`, `max_recipients`, `send_via`, `mps`, `total` and every status counter. A new Broadcast created outside the API may only carry the doctype defaults. Recipient rows cannot be created or changed outside the API either (the doctype `validate` throws), and the Recipient permissions are read-only for System Manager and Huf Admin. The runner and webhook code write through raw SQL or `frappe.db.set_value`, which skip `validate`.
- A recipient row may carry `consent_source` and `consent_at`. They are stored for audit and do not replace the attestation.

Intake (`add_broadcast_recipients`, only while the broadcast is `Draft`) processes each row in this order:

1. The number is normalised to digits-only E.164. It must have 8 to 15 digits. A BSUID is kept verbatim. Anything else goes to `invalid` (reason `invalid_number`) and is not stored.
2. A recipient already in this broadcast is reported in `skipped` with reason `duplicate` and not stored.
3. If the count of non-skipped rows has reached the cap, the row is reported as `skipped` with reason `max_recipients` and not stored. The cap is `max_recipients` (default 1000, at most 10000; the doctype default is 1000).
4. If the broadcast already stores 50000 rows (skipped rows count), the row is reported as `skipped` with reason `row_ceiling` and not stored.
5. Policy check. A matching row is stored with status `skipped` and `skip_reason`:
   - `bsuid_recipient`: a BSUID cannot be a recipient, send to the phone number.
   - `opted_out`: the contact sent STOP (`gateway_service.is_opted_out`).
   - `marketing_opted_out`: MARKETING template only; the contact stopped marketing (`account_events.is_marketing_allowed`).
   - `us_plus_one_marketing`: MARKETING template only; the number has 11 digits and starts with `1`. This also matches Canada and other NANP numbers (section 12).
6. Otherwise the row is stored as `queued`.

Limits per call: at most 10000 recipients per request (`too_many_recipients`), CSV text at most 2 MB (`csv_too_large`). The counters are recomputed at the end of every intake call. `skipped` and `invalid` in the response are capped at 200 entries each; `skipped_total` and `invalid_total` are exact.

CSV: the first header cell matching `phone`, `recipient`, `phone_number`, `mobile`, `wa_id`, `whatsapp` or `number` (case, spaces and dashes ignored) is the recipient column. All other columns become `params.body`, in column order. A leading BOM is stripped. Blank lines are skipped. A CSV without such a header is `invalid_params`.

Before each send the STOP check, the BSUID check, and, for a MARKETING template, the marketing preference are checked again (section 4). A contact that opted out after intake is marked `skipped`.

## 3. Recipient state machine

Each recipient is one `WhatsApp Broadcast Recipient` row (name `<broadcast>-<recipient>`, also used as the `opaque_ref`). The `status` field holds the state.

```
queued ──claim──> sending ──> sent ──> delivered ──> read
  ^                  │         │
  │                  ├──> failed            (failed never overwrites delivered or read)
  │                  ├──> deferred ──(next_attempt_at)──> sending
  │                  ├──> unknown           (never resent automatically; a later sent/delivered/read webhook advances it)
  │                  └──> skipped           (also 131049, terminal)
  └── queued/deferred rows may also become skipped (STOP, marketing stop, cancel)
```

- **Claim.** The sender moves a row to `sending` with `UPDATE ... SET status='sending', attempts=attempts+1 WHERE name=? AND status IN ('queued','deferred') AND attempts < 5` and commits before calling Meta. If it matches no row, another worker owns it (`lost_claim`). A `queued` or `deferred` row that already has 5 attempts cannot be claimed; the sender marks it `failed` with "Gave up after the maximum number of attempts."
- **Release.** If, after the claim, the broadcast is not `Running`, nothing was posted and the row is handed back to the status it had before (a `deferred` row keeps its `next_attempt_at`) and the attempt is given back. If the broadcast is `Cancelled` the row becomes `skipped` with reason `cancelled`.
- **Rank.** Webhooks only move a row forward. Ranks: `queued`/`deferred` 0, `sending` 1, `unknown` 1.5, `sent` 2, `failed` 2.5, `delivered` 3, `read` 4. An update with a rank that is not higher is ignored, so replays and out-of-order webhooks are no-ops. A `skipped` row is never changed by a webhook. Meta `played` is stored as `read`.
- **Webhook match.** A status is matched to a row by `wamid`, else by `biz_opaque_callback_data` (the row name), and only if the row's broadcast belongs to the gateway that received the webhook. A `wamid` is written onto a row that lacks one. A webhook can arrive while the runner has not yet written its result (row still `sending`); the webhook advances the row, and the runner's later write then only persists `wamid`, `message_status` and `sent_at` without touching `status` (`_persist_send_result`), so the held ratio is not under-counted.
- **Unknown.** After the request was attempted, an outcome with no Meta error code (timeout, dropped connection, unreadable response, missing message id, or the result could not be written) is `unknown`. Rows left in `sending` for more than 10 minutes (by `modified`) are moved to `unknown` by `resume_stale` (cron `*/5 * * * *`). `unknown` is never sent again automatically. A later `sent`, `delivered`, `read` or `failed` webhook advances it (`unknown` ranks below `sent`).
- **Counters.** `total`, `queued`, `sending`, `sent`, `delivered`, `read`, `failed`, `deferred`, `unknown`, `skipped` on the broadcast. Webhooks move them by atomic deltas. `recount()` recomputes them from the rows (the rows are the source of truth). It runs after each intake call, after each chunk and at the end of a tick, at completion, on cancel, in `resume_stale` for stale rows and for every Running broadcast.

No WhatsApp Send Key rows are written by a broadcast.

## 4. Sending one recipient

Order of checks in `send_one`:

1. Claim (above).
2. Broadcast must be `Running`, else release.
3. Per-broadcast cap: if rows already started (`sending`, `sent`, `delivered`, `read`, `unknown`, `failed`), including this one, exceed `max_recipients`, the row becomes `skipped` with reason `max_recipients`.
4. STOP and BSUID check. A refusal makes the row `skipped` with the refusal code (`opted_out`, `bsuid_recipient`).
5. The template row must exist with a readable status and category. Otherwise the row is `failed` ("template_missing") and the broadcast pauses with reason `template_missing`.
6. `send_via=marketing_messages` with a non-MARKETING template: row `failed` (`mm_requires_marketing_template`).
7. The bridge send (`force_graph=True`, `biz_opaque_callback_data` = row name, truncated to 256 characters). Inside it, before the POST: a disconnected gateway is refused; the template must belong to the account; the template must be `APPROVED` (else `template_not_approved`); for a MARKETING template the marketing preference is checked (`marketing_opted_out`).
8. Success stores `wamid`, `message_status` (`accepted`, `held_for_quality_assessment`, or empty), `sent_at`, and status `sent`.

The runner acts as a user who holds write permission on the Gateway (section 5).

## 5. Lifecycle, runner and pacing

Broadcast `status`: `Draft`, `Queued`, `Running`, `Paused`, `Completed`, `Cancelled`, `Failed`. `Queued` and `Failed` exist in the doctype but no code sets them.

| Action | Allowed from | Result |
|---|---|---|
| Create | none | `Draft`. Category, template name and account are snapshotted. |
| Add recipients | `Draft` only (`not_draft` otherwise) | Rows added as `queued` or `skipped`. Resets the consent attestation. |
| Attest consent | `Draft`, `Paused` | Records the attestation. |
| Preview | any | Computes limits and cost, stores `cost_estimate` on the broadcast. No sends. |
| Start | `Draft` only | Checks below, then `Running`, `started_by`, `started_at`, first tick enqueued. |
| Pause | `Running` | `Paused`, `pause_reason` set (truncated to 140 characters). A pause on another state does nothing and returns success. |
| Resume | `Paused` | Same checks as start. Records `resumed_by: <user>` as a comment; the resumer becomes the runner identity (ticks run as the resumer). `started_by` is kept. |
| Cancel | any state except `Completed`, `Cancelled` | `Cancelled`, `finished_at` set. `queued` and `deferred` rows become `skipped` with reason `cancelled`. `sending` rows finish. |
| Complete | `Running` | Set by the runner when no `queued`, `deferred` or `sending` row remains; `finished_at` set. |

Start and resume are refused (an exception with a message) unless all of these hold:

- the status is allowed (above);
- consent is attested and the broadcast has a gateway;
- the caller is an enabled user with write permission on the Gateway;
- preview has no `blocking` entry: the template exists and is `APPROVED`, consent attested, no other broadcast `Running` on the gateway, number quality is not RED, and, when the tier is known, queued recipients fit in the remaining 24-hour budget (section 6);
- at least one `queued` or `deferred` row exists;
- no other broadcast is `Running` on the same gateway (re-checked under a lock on the Gateway row).

Start on a `Paused` broadcast is refused ("it can only be started from Draft"); a Paused broadcast goes through `resume_broadcast`, so the person who resumes is authorised and recorded. The write-permission check runs as the caller through `_acting_as`, a context manager that switches user only when the caller differs from the session user, and afterwards restores `session.user`, `sid`, `data` (CSRF token) and the swapped request locals (`form_dict`, cache, role permissions and others) that `frappe.set_user` resets. This is meant to keep the operator's session valid after `start_broadcast`/`resume_broadcast`; it is covered by unit tests only, not by a test through a real HTTP request.

`start_broadcast` additionally requires `confirm_count` to equal the number of `queued` plus `deferred` rows. Start does not read gateway health; only a disconnected connection stops sends (section 9).

### Runner

- One live tick per broadcast, enforced by a cache lock (`huf:<site>:wa_broadcast_tick:<broadcast>`, a random token, TTL 600 s, refreshed at least every 30 s, every 20 sends and after each chunk; a tick that loses the lock exits). Job ids are site-scoped. Queue `long`, job timeout 1800 s.
- A tick works for 240 s. If `queued` rows remain it re-enqueues itself. If only future `deferred` rows (or in-flight `sending` rows) remain, the tick ends as `idle`; the `*/5` cron `resume_stale` revives a Running broadcast with no live lock (also when due `deferred` rows remain after a tick). Revival may take up to about 5 minutes.
- The runner acts as the latest resumer (recorded as a `resumed_by:` comment) or, if none, `started_by`. Write permission on the Gateway is re-checked on every chunk and at least every 50 sends; a disabled user or lost permission pauses the broadcast with reason `permission_lost`.
- Status is re-read before every send, so a pause or cancel stops the tick within one send.

### Pacing

- Rate is `min(mps, throughput)` messages per second. `mps` on the broadcast defaults to 10 (doctype default; code fallback 20 if empty). `throughput` is the value read from Meta when it is an integer or a dict with an integer `mps`; otherwise 80.
- Batch size: 20 for the first batch of a tick; afterwards the number of rows already processed in this tick, at least 20 and at most 200.
- Held ratio: over the last 50 rows with a `sent_at`, if at least 10 exist and more than 30% have `message_status = held_for_quality_assessment`, the rate becomes a quarter of the rate (minimum 1 per second) and batches are halved.

## 6. Limits and preview

`preview_broadcast` returns `limits` (from `broadcast_limits.preview`), `cost`, `confirm_required`, `queued`.

- **Messaging limit.** Read with `GET /<PHONE_NUMBER_ID>?fields=whatsapp_business_manager_messaging_limit,quality_rating,throughput`, cached for 10 minutes. A failure leaves all values unknown and never raises. Tier mapping in code: `TIER_250` 250, `TIER_1K` 1000, `TIER_2K` 2000, `TIER_10K` 10000, `TIER_100K` 100000, `TIER_UNLIMITED` no limit. Only `TIER_250` is confirmed against Meta's page; the other spellings are not (section 11).
- **24-hour budget.** `remaining_24h` = tier maximum minus distinct recipients with a `sent`, `delivered`, `read` or `unknown` row sent in the last 24 hours, or a `sending` row modified in the last 24 hours, across all broadcasts on the gateway. `failed`, `deferred` and `skipped` rows do not use budget. If `queued` rows exceed it, preview blocks with `recipients_exceed_24h_budget:<queued>><remaining>`. If the tier is unknown, preview only warns ("Messaging limit is unknown") and `max_recipients` is the only ceiling. Unlimited tier: `within_limit` true.
- **Quality.** `RED` blocks start (`quality_red`). `YELLOW` warns. Any other value is unknown.
- **Template.** A missing template blocks (`template_not_found`), a non-`APPROVED` one blocks (`template_not_approved:<STATUS>`).
- `queued`, `skipped` and `recipients` in the preview are row counts by status (`queued` counts only `queued`; the endpoint's own `queued` and the confirm count also include `deferred`).

Blocking reasons: `broadcast_not_found`, `template_not_found`, `template_not_approved:<status>`, `consent_not_attested`, `another_broadcast_running:<names>`, `quality_red`, `recipients_exceed_24h_budget:<n>><m>`, `preview_failed`. Warnings: US `+1` queued recipients (redundant for a MARKETING broadcast, since intake already skips them), quality YELLOW, messaging limit unknown.

## 7. Errors, pause signals and retries

Classification uses `whatsapp_errors`. A send that gets no Meta error code is `unknown` (section 3). A refused send raised before the POST has no Meta code and is handled as shown in the first rows.

| Situation | Row outcome | Broadcast |
|---|---|---|
| `opted_out`, `marketing_opted_out`, `bsuid_recipient` | `skipped` (reason) | Continues |
| `gateway_disconnected` | `deferred` 300 s | Pauses (`gateway_disconnected`) |
| `template_not_approved` | `failed` | Pauses (`template_not_approved`) |
| Template missing or unreadable | `failed` | Pauses (`template_missing`) |
| `mm_requires_marketing_template` | `failed` | Continues |
| Other refusal before the POST | `failed` | Continues |
| No Meta error code after the POST (timeout, connection error, HTTP 5xx or 429 without a Meta error code, unparseable response) | `unknown` | Continues |
| 131049 per-user marketing limit (send response) | `skipped`, `skip_reason` `per_user_marketing_limit`, `error_code` 131049 kept; never auto-resent | Continues |
| 130429 throughput, 131056 pair limit | `deferred`, retryable | Continues |
| 131057 account maintenance, 131016, 1, 2 (server); 4, 17, 32, 613, 80007 (API rate limits) | `deferred`, retryable | Continues |
| 131050 user stopped marketing (send response) | `failed`; a marketing stop is recorded, which skips the contact's other pending rows | Continues |
| 131026, 131047, 131048, 132000, 132001, 132005, 132007, 132012, and any code not listed above (including 131062, which has no table entry; the HTTP status is not used to classify a coded error) | `failed`, `error_code` stored | Continues |
| 132015 template paused, 132016 template disabled, 135000, 131042 | `failed`, `error_code` stored | Pauses (`meta_error_<code>`) |

Retry rules:

- A retryable error is retried until the row has made 5 POST attempts (`attempts` counts claims); the fifth failure is `failed`. 131049 is not retryable: it is a terminal skip.
- Backoff after attempt n: 2, 4, 8, 16 s (doubling, capped at 16 s, +/-20% jitter); 131056 is a fixed 6 s; 60 s if no backoff is available. Gateway disconnected is 300 s.
- There is no per-recipient retry. A `failed` row is a permanent Meta verdict, and `unknown` may already have been delivered. To reach the contacts again, create a new, separately attested broadcast.

Pause rules (the runner stops sending, rows stay as they are; resume is manual):

| Signal | Source | Reason stored |
|---|---|---|
| `pause_broadcast` | operator | `manual` |
| `pause_all_broadcasts` | operator | `kill_switch` |
| Send response 132015, 132016, 135000, 131042 | send | `meta_error_<code>` |
| Status webhook `failed` with code 135000 on a row that advances | webhook | `WhatsApp error 135000 (messages dropped by pacing)` |
| Template webhook: status `PAUSED`, `DISABLED`, `REJECTED` | `message_template_status_update` | `template:paused`, `template:disabled`, `template:rejected` |
| Template quality turns `RED` | `message_template_quality_update` | `template:quality_red` |
| Template category changes to `MARKETING` | `template_category_update` | `template:category_marketing` |
| Gateway disconnected, template not approved or missing at send | send | see table above |
| Write permission lost | each chunk, every 50 sends | `permission_lost` |

Template webhooks pause Running broadcasts on the same WhatsApp account whose `template_name` matches.

Webhook handling: `sent`, `delivered`, `read`, `played` move a row forward. `failed` stores the first error's code and message, unless the row is `delivered`/`read`. A webhook handler failure never breaks webhook ingest. A status `failed` with 131050 marks that row `failed` and records a marketing stop (the same consent record as the send path), which skips the contact's other pending rows. A status `failed` with 131049 turns the row into `skipped` (`per_user_marketing_limit`, `error_code` kept, `failed_at` not set) unless it is already `delivered`/`read`; it is never resent. A `sent` webhook resolves an `unknown` row. The `user_preferences` event (marketing stop) and a STOP keyword both skip the contact's `queued` and `deferred` rows (reason `opted_out`) in broadcasts of that gateway in `Queued`, `Running` or `Paused` state; `Draft` rows are re-checked at send time instead.

## 8. Costs

The estimate comes from `huf/ai/whatsapp/broadcast_rates.json`. Today every rate in that file is `null` and `rates_verified` is `false`, because the official per-country rate card was not retrievable. As a result:

- `cost.total` is `null` and each market has a `rate_unavailable:<category>:<market>` warning. The wizard shows "unavailable".
- Recipients whose country code is not in the file are counted under `UNKNOWN` with a `market_unknown:<n>_recipients` warning.
- The estimate becomes a number only after rates are filled in from Meta's official rate card and the file's source and date are updated.

The estimate covers `queued` and `deferred` rows. It is never an invoice; Meta billing is the source of truth. The typed-count confirmation is a separate guard against starting a list that changed after the preview.

## 9. API reference

All methods are in `huf/ai/whatsapp/management.py`, whitelisted, behind the bridge guard. Failures from a guarded call return `{"success": false, "error": <code>, "message": ...}`; a missing permission raises a permission error. Write methods need write permission on the broadcast's Gateway (or the integrations-manage capability). Read methods need read permission. Every mutating call writes an audit log line (`huf.whatsapp.broadcast`) and a comment on the broadcast. POST methods are rate limited per user: 60 calls per 60 s, except `start_broadcast` and `pause_all_broadcasts` (30 per 60 s).

| Method | Needs | Parameters | Returns | Error codes |
|---|---|---|---|---|
| `create_broadcast` | write | `gateway`, `template` (name or `<name>-<lang>`), `title`, `language_code`, `body_params`, `header_params`, `button_params`, `consent_source`, `max_recipients` (1 to 10000), `mps`, `send_via` (`messages` or `marketing_messages`) | `success`, `broadcast`, `status` (`Draft`), `category` | `invalid_gateway`, `not_found`, `no_account`, `invalid_name`, `invalid_title`, `template_not_found`, `template_not_approved`, `invalid_send_via`, `mm_requires_marketing_template`, `invalid_max_recipients`, `invalid_params` |
| `add_broadcast_recipients` | write (Draft only; resets attestation) | `broadcast`, `recipients` (list of numbers or `{recipient, params, consent_source, consent_at}`), `csv_text` | `success`, `added`, `skipped`, `skipped_total`, `invalid`, `invalid_total` | `not_found`, `not_draft`, `csv_too_large`, `too_many_recipients`, `invalid_params`, `no_recipients` |
| `attest_broadcast_consent` | write | `broadcast`, `consent_source` | `success`, `broadcast`, `consent_attested`, `consent_source` | `not_found`, `invalid_state`, `consent_source_required` |
| `preview_broadcast` | write | `broadcast` | `success`, `broadcast`, `status`, `consent_attested`, `limits`, `cost`, `confirm_required`, `queued` | `not_found` |
| `start_broadcast` | write (Draft only) | `broadcast`, `confirm_count` | `success`, `broadcast`, `status` (`Running`), `queued` | `not_found`, `consent_not_attested`, `no_recipients`, `confirm_mismatch`; runner refusals are raised as validation errors with a message (`Broadcast blocked: ...`, `Another broadcast (...) is already running on this Gateway`, wrong state, no consent, no queued recipients) |
| `pause_broadcast` | write | `broadcast` | `success`, `broadcast`, `status` | `not_found` |
| `resume_broadcast` | write (Paused only) | `broadcast` | `success`, `broadcast`, `status`, `queued` | `not_found`; same runner refusals as start |
| `cancel_broadcast` | write | `broadcast` | `success`, `broadcast`, `status` | `not_found`; raises if already `Completed` or `Cancelled` |
| `pause_all_broadcasts` | write | `gateway` | `success`, `gateway`, `paused` (names of broadcasts that were Running) | `invalid_gateway`, `not_found` |
| `list_broadcasts` | read | `gateway` (required unless admin), `status`, `limit` (default 50, max 200), `offset` | `success`, `broadcasts` (each with `counts` object, parsed params, ISO times) | `not_found`, `gateway_required` |
| `get_broadcast` | read | `broadcast` | `success`, `broadcast` | `not_found` |
| `list_broadcast_recipients` | read | `broadcast`, `status`, `limit` (default 100, max 200), `offset` | `success`, `recipients` (`name`, `recipient`, `status`, `skip_reason`, `wamid`, `message_status`, `attempts`, `next_attempt_at`, `error_code`, `error_message`, `sent_at`, `delivered_at`, `read_at`, `failed_at`) | `not_found` |

A caller with read but not write permission sees recipient numbers masked to the last four digits, and digit runs of seven or more are masked in `name` and `error_message`.

The Meta endpoints used: `POST /<PHONE_NUMBER_ID>/messages` or `/marketing_messages` (per recipient, with `biz_opaque_callback_data`), and `GET /<PHONE_NUMBER_ID>?fields=whatsapp_business_manager_messaging_limit,quality_rating,throughput`. Webhook fields consumed: `messages` (statuses), `message_template_status_update`, `message_template_quality_update`, `template_category_update`, `user_preferences`.

## 10. Marketing Messages API (`send_via`)

`send_via=marketing_messages` posts the same payload to `/marketing_messages`. It is refused for a non-MARKETING template at create (`mm_requires_marketing_template`) and per recipient (row `failed`). The wizard offers the choice for MARKETING templates.

- Huf does not send `product_policy` or `message_activity_sharing`; the account default applies.
- Status webhooks may report a different pricing category for these sends. Huf does not use it.
- Onboarding to the Marketing Messages API and the dates after which Cloud API marketing sends stop are Meta facts that were not confirmed here (section 11). Whether the 131049 limit behaves the same on this path is not known; the same terminal skip applies.

## 11. Unverified Meta facts

The code works without these, but they should be confirmed against Meta before relying on them:

- Placement and size of `biz_opaque_callback_data` on the send body (top level, truncated to 256 characters in code; Meta may allow 512) and that status webhooks echo it. Rows are also matched by `wamid`.
- Tier enum spellings other than `TIER_250` (`TIER_1K`, `TIER_2K`, `TIER_10K`, `TIER_100K`, `TIER_UNLIMITED`) and the downgrade rules.
- The shape of the `throughput` field. Only an integer or an integer `mps` key is read.
- Error 135000. Meta's error-code page describes it as a generic invalid-parameter error. Huf treats it as a pause signal (portfolio pacing drop) conservatively, so an unrelated 135000 also pauses.
- Pair-limit numbers (the 6 s delay for 131056) and per-user marketing limit behaviour (131049) on either send path.
- That WhatsApp does not deliver marketing templates to US `+1` numbers, and since when.
- The 2027-04-13 and 2027-10-13 dates for Cloud API marketing messages, taken from track research and not stated on the send-messages page.
- Meta rate cards (not used; section 8).
- `quality_rating` values beyond `GREEN` (`YELLOW`, `RED` are assumed).

## 12. Known limits

### Known issues / open items

- **Bridge loses the message id on an exception after the POST (M6).** In `whatsapp_bridge.send_template`, bookkeeping after the Graph POST (`policy.note_template_sent`) can raise. The runner then marks the row `unknown` and the wamid is not stored; recovery depends on Meta echoing `biz_opaque_callback_data` in the status webhook. Not fixed. A `BridgeError` raised after the POST would mark an accepted message `failed`. Not verified in this pass.
- **`biz_opaque_callback_data` placement unverified.** Top-level placement on the send body, the length limit and the echo in `statuses[]` were not confirmed against Meta (section 11). Confirm on the test number before relying on row-name matching.
- **Resolution of `unknown` is webhook-only.** There is no action. A late `sent`/`delivered`/`read` webhook resolves the row; if none arrives it stays `unknown`.
- **Sent/held race.** If a `sent` webhook beats the runner's write, the row status is correct and `message_status` is persisted afterwards without a status condition. Rows whose result cannot be written at all stay `unknown`. The race is covered by unit tests; no live check exists.
- **Cancel/pause race.** A send that already read the broadcast as Running just before a cancel still posts (milliseconds; "in-flight finish").
- **Fixtures.** The 135000/131049/131050 webhook fixtures are Huf-authored, not captured from Meta.
- **`_acting_as` through a real request** is not covered by an automated test (section 4).


- **US `+1` filter also skips Canada.** The rule is any 11-digit number starting with `1`, for MARKETING templates only.
- **No per-recipient retry.** `failed`, `skipped` and `unknown` rows are not resent by any action.
- **`unknown` rows are never auto-resent.** A `sent`, `delivered` or `read` webhook moves them forward.
- **STOP keyword, `user_preferences` marketing stop and send-time 131050 all skip the contact's `queued` and `deferred` rows** in other unfinished broadcasts of the gateway. A 131050 arriving by status webhook also records the marketing stop and skips them.
- **A template that is paused, disabled, rejected, quality RED, or whose category changes to MARKETING pauses running broadcasts** that use it, until someone resumes. Resume re-runs the start checks.
- **One Running broadcast per gateway.**
- **135000 pauses conservatively** (section 11).
- **Tier unknown means no budget check.**
- **Idle revival delay.** A broadcast with only future `deferred` rows is revived by the cron, up to about 5 minutes late.
- **Held messages are not a delivery signal.** `held_for_quality_assessment` means Meta accepted the request but holds it; the final result arrives by webhook.
- **Cost estimate is unavailable** until rates are filled in.
- **No inbox, no scheduling.**

## 13. Operations

- **Kill switch.** `pause_all_broadcasts(gateway)` (the "Stop all broadcasts" button in the broadcast tab) pauses every Running broadcast on the gateway with reason `kill_switch`. A tick stops before its next send. Rows in `sending` at that moment finish. Resume is manual per broadcast.
- **Recount.** Counters are reconciled automatically (section 3). To force it for one broadcast, run `frappe.get_doc("WhatsApp Broadcast", name).recount(commit=True)` in a bench console on the site. Counters can differ from the rows only briefly, while webhooks apply deltas.
- **Resolving an `unknown` row.** There is no action for it. Look up the recipient in WhatsApp Manager's message log or the business inbox. If the message was delivered, a later `delivered` or `read` webhook matched by `wamid` or row name updates the row. If not delivered, leave it; do not resend inside this broadcast. To message the contact again, include them in a new broadcast.
- **131049 is final for the broadcast.** The row is `skipped` and the broadcast can complete; there is no 24-hour deferral. Include the contact in a new broadcast later if appropriate.
- **Stuck broadcast.** If a Running broadcast does not progress, wait for the `*/5` cron (`resume_stale`) which also turns stale `sending` rows into `unknown` and revives the tick. If it is `Paused`, read `pause_reason`, fix the cause, then resume.
- **Audit.** Each mutating call leaves a comment on the broadcast; resume leaves `resumed_by: <user>`.
- **After a pause for 132015, 132016, 135000, 131042.** Check the template and account notices in WhatsApp Manager before resuming.

## 14. Meta references

- Send messages: <https://developers.facebook.com/documentation/business-messaging/whatsapp/messages/send-messages>
- Messaging limits: <https://developers.facebook.com/documentation/business-messaging/whatsapp/messaging-limits>
- Throughput: <https://developers.facebook.com/documentation/business-messaging/whatsapp/throughput>
- Template pacing: <https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/template-pacing>
- Status webhook: <https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/reference/messages/status>
- Pricing: <https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing>
- Error codes: <https://developers.facebook.com/docs/whatsapp/cloud-api/support/error-codes>
