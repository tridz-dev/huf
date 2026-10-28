# WhatsApp Broadcast

A WhatsApp Broadcast sends one approved template to a bounded list of recipients through the Meta WhatsApp Cloud API. The list is typed or pasted in, or built from saved, consented lists called audiences (section 15). It is an automation tool. It is not a campaign platform, a CRM, or an inbox: there is no scheduling, no A/B testing, and replies are not handled by the broadcast (they arrive through the normal inbound flow).

**Principle.** Huf follows Meta's rules and nothing else is hard-wired. Every other limit Huf applies is a named, visible setting with a default, a range and a stated reason: Settings tab of the WhatsApp page, **Broadcast limits** (API: `get_broadcast_limits` / `update_broadcast_limits`, section 14). The full table is in [BROADCAST_LIMITS.md](BROADCAST_LIMITS.md), which is generated from the registry in `broadcast/policy.py`. Broadcasts do not use the agent recipient allowlist (section 2).

This document describes the code as it is. Statements that depend on Meta behaviour that was not confirmed are listed in [section 11](#11-unverified-meta-facts). The live check plan is in [broadcast-live-verification.md](broadcast-live-verification.md). The operator summary is in the [gateway runbook](../gateways/whatsapp-runbook.md#10-broadcasts).

Code: `huf/ai/whatsapp/broadcast/` (`policy.py` limits registry, `api_limits.py` limits API, `recipients.py` intake, `send.py` one recipient, `runner.py` lifecycle and pacing, `status.py` Meta statuses and stops, `limits.py` limit and preview, `checks/start_gate.py` start gating, `checks/audience_check.py` purpose check, `cost.py` estimate, `api.py` whitelisted API, `audiences/` audience API, import and wiring), doctypes `WhatsApp Broadcast`, `WhatsApp Broadcast Recipient`, `WhatsApp Broadcast Settings` (single), `WhatsApp Audience`, `WhatsApp Audience Member` and `WhatsApp Broadcast Audience` (child table of the broadcast).

## 1. Scope

In scope:

- One template per broadcast. One request per recipient (`type: template`). Meta offers no multi-recipient send.
- Per-recipient parameters, merged over the broadcast defaults per part (`body`, `header`, `button`). The wizard collects body variables, a header value (text, or an https link for an image, video or document header) and url / copy-code button values; templates with a location header cannot be broadcast from the wizard (use the API).
- **Location header.** The wizard asks for latitude (-90 to 90), longitude (-180 to 180) and an optional place name and address (1000 characters each); invalid values are refused in the wizard and by `create_broadcast`.
- **Per-recipient values.** Paste (or upload) a list whose first line is a header: `phone`, then optional `header` (text, or an https link for a media header), `header_lat` / `header_lng` / `header_name` / `header_address`, `button_url_<n>` (link suffix, no scheme) and `button_code_<n>` (copy code, 15 letters or digits). Any other column is a body variable, in order. An empty cell uses the broadcast default; a recipient button replaces the default of the same index. A row with a bad value is reported under `invalid` (`invalid_params: ...`) and not stored.
- **Live progress.** While a broadcast is open, the page shows a green **Live** dot when the socket is connected and a grey **Polling** dot otherwise. Huf publishes `wa_broadcast_progress` (status and counters, at most every 2 s, always on a lifecycle change) to the broadcast's document room, so only users who can read the broadcast receive it. Polling stays as the fallback (5 s without the socket, a 30 s reconcile with it).
- A Draft can be edited until it starts: remove one recipient, or delete the whole Draft. Closing the wizard before starting discards its Draft. Template values are fixed once recipients are added.
- An expired or invalid access token (Meta error 190 / 102) pauses the broadcast with `pause_reason=meta_error_190` and keeps every row sendable; fix the token and resume.
- Recipients from a list of numbers, a CSV text, or saved audiences (section 15).
- Preview with coded blocking issues and overridable warnings, and a typed-count confirmation before start (section 14).
- Pause, resume, cancel, and a gateway-wide kill switch.
- Delivery tracking from Meta status webhooks.
- Two send paths, chosen by `send_via`: `messages` (`POST /<PHONE_NUMBER_ID>/messages`, default) and `marketing_messages` (`POST /<PHONE_NUMBER_ID>/marketing_messages`, MARKETING templates only; section 10).

Not implemented:

- Retry of failed rows. There is no endpoint (`retry_failed_broadcast_recipients` does not exist, by design; section 7).
- Scheduling a start time.
- Groups and free-form messages. Broadcasts send templates only.
- Cost in the preview while no rates are filled in (section 8).
- A shared sending-speed budget across broadcasts of one gateway. By default only one broadcast runs per gateway; the `one_active_per_gateway` safety can be switched off, in which case broadcasts run side by side with no shared pacing (section 14).

## 2. Consent and recipient intake

A broadcast may only reach people who opted in.

- Meta requires opt-in for any business-initiated message. Huf's record of it is the consent attestation. It is on by default (`require_consent_attestation`, section 14); the checkbox is Huf's record, not something Meta checks.
- Consent can come from the audiences the broadcast uses (each audience carries its own attestation, section 15) or from the broadcast itself. Per broadcast, an operator attests with `attest_broadcast_consent`. It stores `consent_source` (required, non-empty), `consent_attested_by`, `consent_attested_at`, `consent_attested`. Start is refused until it is set (when the setting is on). Attestation is allowed in `Draft` and `Paused`. `add_broadcast_recipients`, `remove_broadcast_recipient` and `set_broadcast_audiences` (Draft only) reset the attestation (`consent_attested` 0, by/at/source cleared), so the attestation always covers the list as it is now. `set_broadcast_audiences` sets it again by itself when every sendable row comes from an audience with a recorded attester (section 15); any manually added row needs the broadcast's own attestation.
- Writes to a Broadcast through generic REST, the desk form or `doc.save` are rejected unless they go through the broadcast API. Guarded fields: the consent fields, `gateway`, `template`, `whatsapp_account`, `status`, `started_by`, `started_at`, `finished_at`, `pause_reason`, `max_recipients`, `send_via`, `mps`, `total` and every status counter. A new Broadcast created outside the API may only carry the doctype defaults. Recipient rows cannot be created or changed outside the API either (the doctype `validate` throws), and the Recipient permissions are read-only for System Manager and Huf Admin. The runner and webhook code write through raw SQL or `frappe.db.set_value`, which skip `validate`.
- A recipient row may carry `consent_source` and `consent_at`. They are stored for audit and do not replace the attestation.

Intake (`add_broadcast_recipients`, only while the broadcast is `Draft`) processes each row in this order:

1. The number is normalised to digits-only E.164. It must have `min_phone_digits` (8 by default, setting) to 15 digits (15 is E.164, set by the standard). A BSUID is kept verbatim. Anything else goes to `invalid` (reason `invalid_number`) and is not stored.
2. A recipient already in this broadcast is reported in `skipped` with reason `duplicate` and not stored.
3. If the count of non-skipped rows has reached the cap, the row is reported as `skipped` with reason `max_recipients` and not stored. The cap is the broadcast's own `max_recipients` if set, else `max_recipients_default` (1000), bounded by `max_recipients_ceiling` (10000); `0` stored for either setting means no limit.
4. If the broadcast already stores `max_rows_per_broadcast` rows (50000 by default; skipped rows count), the row is reported as `skipped` with reason `row_ceiling` and not stored.
5. Policy check. A matching row is stored with status `skipped` and `skip_reason`:
   - `bsuid_recipient`: a BSUID cannot be a recipient, send to the phone number.
   - `opted_out`: the contact sent STOP (`gateway_service.is_opted_out`).
   - `marketing_opted_out`: MARKETING template only; the contact stopped marketing (`account_events.is_marketing_allowed`).
   - `us_plus_one_marketing`: MARKETING template only; the number has 11 digits and starts with `1`. This also matches Canada and other NANP numbers (section 12).
6. Otherwise the row is stored as `queued`.

Limits per call (all settings, defaults shown): at most `max_rows_per_request` 10000 recipients per request (`too_many_recipients`), CSV text at most `max_csv_mb` 2 MB (`csv_too_large`). The counters are recomputed at the end of every intake call. `skipped` and `invalid` in the response are capped at 200 entries each (`returned_list_limit`, internal); `skipped_total` and `invalid_total` are exact.

A row added from an audience carries the audience name (`audience` on the recipient row) and goes through the same steps, so STOP, BSUID, US `+1` and the caps are checked in this one place.

CSV: the first header cell matching `phone`, `recipient`, `phone_number`, `mobile`, `wa_id`, `whatsapp` or `number` (case, spaces and dashes ignored) is the recipient column. All other columns become `params.body`, in column order. A leading BOM is stripped. Blank lines are skipped. A CSV without such a header is `invalid_params`.

Before each send the STOP check, the BSUID check, and, for a MARKETING template, the marketing preference are checked again (section 4). A contact that opted out after intake is marked `skipped`.

> **Who can be messaged.** A broadcast sends to the recipients its operator listed or picked from audiences (after the opt-out, marketing-preference and +1 filters in this section). It does **not** use the gateway's agent recipient allowlist (`agent_recipient_scope` / `agent_recipient_allowlist`), which only limits what an *agent* may send. The broadcast code has no allowlist step: broadcasts follow Meta's rules (opt-in, STOP, per-user marketing limits, messaging tier) and the configurable limits of section 14. Check the list before you start; the typed-count confirmation (when on) is the last guard.

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

- **Claim.** The sender moves a row to `sending` with `UPDATE ... SET status='sending', attempts=attempts+1 WHERE name=? AND status IN ('queued','deferred') AND attempts < <max_attempts>` (`max_attempts`, default 5) and commits before calling Meta. If it matches no row, another worker owns it (`lost_claim`). A `queued` or `deferred` row that already has the maximum number of attempts cannot be claimed; the sender marks it `failed` with "Gave up after the maximum number of attempts."
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
3. Per-broadcast cap (the broadcast's own `max_recipients` field only): if rows already started (`sending`, `sent`, `delivered`, `read`, `unknown`, `failed`), including this one, exceed `max_recipients`, the row becomes `skipped` with reason `max_recipients`.
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
- preview has no `blocking` entry other than the two the runner enforces itself (below): the template exists and is `APPROVED`, template values are complete, the gateway is not disconnected, audiences match the template's purpose, at least one queued recipient (section 6);
- for `start_broadcast`: the caller acknowledged exactly the warnings the preview currently shows (`override_warnings`, section 14). Number quality RED and queued recipients above the 24-hour budget are warnings, not blocks;
- consent is attested (when `require_consent_attestation` is on) and no other broadcast is `Running` on the same gateway (when `one_active_per_gateway` is on). Both are re-checked under a lock on the Gateway row; the preview only reports them;
- at least one `queued` or `deferred` row exists.

Start on a `Paused` broadcast is refused ("it can only be started from Draft"); a Paused broadcast goes through `resume_broadcast`, so the person who resumes is authorised and recorded. The write-permission check runs as the caller through `_acting_as`, a context manager that switches user only when the caller differs from the session user, and afterwards restores `session.user`, `sid`, `data` (CSRF token) and the swapped request locals (`form_dict`, cache, role permissions and others) that `frappe.set_user` resets. This is meant to keep the operator's session valid after `start_broadcast`/`resume_broadcast`; it is covered by unit tests only, not by a test through a real HTTP request.

`start_broadcast` additionally requires `confirm_count` to equal the number of `queued` plus `deferred` rows when `require_typed_count` is on and the caller is not authenticated with an API key (section 14). `resume_broadcast` takes no `override_warnings`: it refuses on blocking issues but needs no acknowledgement, and it does not apply the over-budget deferral (section 14). Start does not read gateway health beyond the `Disconnected` connection state, which blocks the preview (`gateway_disconnected`) and stops sends.

### Runner

- One live tick per broadcast, enforced by a cache lock (`huf:<site>:wa_broadcast_tick:<broadcast>`, a random token, TTL 600 s, refreshed at least every 30 s, every 20 sends and after each chunk; a tick that loses the lock exits). Job ids are site-scoped. Queue `long`, job timeout 1800 s.
- A tick works for 240 s (`tick_budget_seconds`, internal; the lock TTL, heartbeat and permission re-check intervals are internal registry rows too). If `queued` rows remain it re-enqueues itself. If only future `deferred` rows (or in-flight `sending` rows) remain, the tick ends as `idle`; the `*/5` cron `resume_stale` revives a Running broadcast with no live lock (also when due `deferred` rows remain after a tick). Revival may take up to about 5 minutes.
- The runner acts as the latest resumer (recorded as a `resumed_by:` comment) or, if none, `started_by`. Write permission on the Gateway is re-checked on every chunk and at least every 50 sends; a disabled user or lost permission pauses the broadcast with reason `permission_lost`.
- Status is re-read before every send, so a pause or cancel stops the tick within one send.

### Pacing

- Rate is `min(wanted, cap)` messages per second. `wanted` is the broadcast's own `mps` if set, else `default_mps` (setting, default 20). `cap` is the speed ceiling: the rate Meta reports when it is an integer or a dict with an integer `mps`; if the operator set `max_mps_cap` in settings it can only lower that (the lower of the two applies, or the setting alone when Meta reports nothing); with neither it is 80.
- Batch size: `ramp_first_batch` (20) for the first batch of a tick; afterwards the number of rows already processed in this tick, at least `ramp_first_batch` and at most `max_batch` (200).
- Held ratio: over the last `held_window` (50) rows with a `sent_at`, if at least `min_held_sample` (10) exist and more than `held_ratio_limit` (30%) have `message_status = held_for_quality_assessment`, the rate becomes a quarter of the rate (minimum 1 per second) and batches are halved. `held_throttle_enabled` (safety, on) switches this off.

## 6. Limits and preview

`preview_broadcast` returns `limits` (from `limits.preview`), `limits_in_effect`, `cost`, `confirm_required`, `queued`. It never raises on a Meta failure; an unexpected error becomes a blocking entry `preview_failed`.

`limits` has: `recipients`, `queued`, `skipped` (row counts by status; `queued` counts only `queued`, while the endpoint's own `queued` and the confirm count also include `deferred`), `category`, `template_status`, `within_limit`, `remaining_24h`, `warnings`, `blocking`, `limits_in_effect`. `warnings` and `blocking` are lists of `{code, message, limit_key}`; `limit_key` is the registry key of the limit behind the issue (or `null`). `limits_in_effect` lists the registry keys that shaped this broadcast, for the wizard's "Limits applied to this broadcast" box.

- **Messaging limit.** Read with `GET /<PHONE_NUMBER_ID>?fields=whatsapp_business_manager_messaging_limit,quality_rating,throughput`, cached for `limits_cache_ttl_seconds` (600, internal). A failure leaves all values unknown and never raises. Tier mapping in code: `TIER_250` 250, `TIER_1K` 1000, `TIER_2K` 2000, `TIER_10K` 10000, `TIER_100K` 100000, `TIER_UNLIMITED` no limit. Only `TIER_250` is confirmed against Meta's page; the other spellings are not (section 11).
- **24-hour budget.** `remaining_24h` = tier maximum minus distinct recipients with a `sent`, `delivered`, `read` or `unknown` row sent in the last 24 hours, or a `sending` row modified in the last 24 hours, across all broadcasts on the gateway. `failed`, `deferred` and `skipped` rows do not use budget. If `queued` rows exceed it, preview gives the **warning** `over_budget` (Huf no longer blocks; Meta's tier is still Meta's rule). If the tier is unknown the warning is `tier_unknown` and `max_recipients` is the only ceiling. Unlimited tier: `within_limit` true, `remaining_24h` null.
- **Quality.** `RED` gives the warning `quality_red`, `YELLOW` the warning `quality_yellow`. Any other value is unknown.
- **Template.** A missing template blocks (`template_unavailable`); a non-`APPROVED` one blocks (`template_not_approved`).

### Issue codes

Blocking (the start is refused; they cannot be acknowledged):

| Code | Meaning |
|---|---|
| `template_not_approved` | Template status is not `APPROVED` (Meta rule; `limit_key` `template_approved_only`). |
| `template_unavailable` | The template record no longer exists. |
| `consent_not_attested` | Consent not attested, while `require_consent_attestation` is on (`limit_key` `require_consent_attestation`). Only reported by the preview; enforced by the runner under the lock. |
| `another_broadcast_running` | Another broadcast is `Running` on the gateway, while `one_active_per_gateway` is on. Only reported by the preview; enforced by the runner. |
| `no_recipients` | No `queued` or `deferred` rows. |
| `missing_params` | Queued recipients are missing template values, carry values the template does not use, or have invalid values (one entry per kind; the message counts recipients and names the variables). |
| `gateway_disconnected` | The Gateway's connection state is `Disconnected`. |
| `audience_purpose_mismatch` | An included audience was not collected for the template category's purpose (section 15). |
| `broadcast_not_found`, `preview_failed` | The broadcast does not exist; the check itself failed. |

Warnings (overridable: the operator acknowledges each code at start):

| Code | Meaning |
|---|---|
| `quality_red` | Number quality is RED. |
| `quality_yellow` | Number quality is YELLOW. |
| `over_budget` | Queued recipients exceed `remaining_24h`. Continuing sends the first `remaining_24h` now and holds the rest for 24 hours (section 14). |
| `tier_unknown` | The tier could not be read; the budget was not checked. |
| `other_broadcast_running` | Other broadcasts are sending from the gateway; only when `one_active_per_gateway` is off. |
| `us_plus_one_marketing` | MARKETING template and queued US `+1` numbers. Intake already skips those, so this appears only for rows queued before the template's category became MARKETING. |

The earlier free-text blocking strings (`recipients_exceed_24h_budget:...`, `quality_red`, `template_not_found`, ...) no longer exist.

## 7. Errors, pause signals and retries

Classification uses `whatsapp_errors`. A send that gets no Meta error code is `unknown` (section 3). A refused send raised before the POST has no Meta code and is handled as shown in the first rows.

| Situation | Row outcome | Broadcast |
|---|---|---|
| `opted_out`, `marketing_opted_out`, `bsuid_recipient` | `skipped` (reason) | Continues |
| `gateway_disconnected` | `deferred` (`gateway_down_defer_seconds`) | Pauses (`gateway_disconnected`) |
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

- A retryable error is retried until the row has made `max_attempts` (5) POST attempts (`attempts` counts claims); the last failure is `failed`. 131049 is not retryable: it is a terminal skip.
- Backoff after attempt n: 2, 4, 8, 16 s (doubling, capped at 16 s, +/-20% jitter); 131056 is a fixed 6 s; 60 s if no backoff is available. Gateway disconnected waits `gateway_down_defer_seconds` (300 s); an access-token error (190 / 102) waits `auth_defer_seconds` (300 s) and gives the attempt back.
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

The estimate comes from `huf/ai/whatsapp/broadcast/rates.json`. Today every rate in that file is `null` and `rates_verified` is `false`, because the official per-country rate card was not retrievable. As a result:

- `cost.total` is `null` and each market has a `rate_unavailable:<category>:<market>` warning. The wizard shows "unavailable".
- Recipients whose country code is not in the file are counted under `UNKNOWN` with a `market_unknown:<n>_recipients` warning.
- The estimate becomes a number only after rates are filled in from Meta's official rate card and the file's source and date are updated.

The estimate covers `queued` and `deferred` rows. It is never an invoice; Meta billing is the source of truth. The typed-count confirmation is a separate guard against starting a list that changed after the preview.

## 9. API reference

Write methods are in `huf/ai/whatsapp/broadcast/api.py` (`huf.ai.whatsapp.broadcast.api.<method>`); read methods (`list_broadcasts`, `get_broadcast`, `get_broadcast_template_params`, `list_broadcast_recipients`) are in `broadcast/api_read.py`; the limits methods are in `broadcast/api_limits.py` (section 14) and the audience methods in `broadcast/audiences/api.py` and `broadcast/audiences/wiring.py` (section 15). All are whitelisted, behind the bridge guard. Failures from a guarded call return `{"success": false, "error": <code>, "message": ...}`; a missing permission raises a permission error. Write methods need write permission on the broadcast's Gateway (or the integrations-manage capability). Read methods need read permission. Every mutating call writes an audit log line (`huf.whatsapp.broadcast`) and a comment on the broadcast. Each call below except `preview_broadcast` is rate limited with Frappe's `rate_limit` over 60 s; the allowed calls per minute are the `rate_*` rows of the limits registry (e.g. `create_broadcast` 60, `remove_broadcast_recipient` 120, `delete_broadcast`, `start_broadcast` and `pause_all_broadcasts` 30) and can be changed (section 14). Frappe's limiter counts per caller address by default; the previous version of this document said "per user", which the code does not do.

| Method | Needs | Parameters | Returns | Error codes |
|---|---|---|---|---|
| `create_broadcast` | write | `gateway`, `template` (name or `<name>-<lang>`), `title`, `language_code`, `body_params`, `header_params`, `button_params`, `consent_source`, `max_recipients` (1 to `max_recipients_ceiling`, 10000 by default; no upper bound when the ceiling is set to no limit), `mps`, `send_via` (`messages` or `marketing_messages`) | `success`, `broadcast`, `status` (`Draft`), `category` | `invalid_gateway`, `not_found`, `no_account`, `invalid_name`, `invalid_title`, `template_not_found`, `template_not_approved`, `invalid_send_via`, `mm_requires_marketing_template`, `invalid_max_recipients`, `invalid_params` |
| `add_broadcast_recipients` | write (Draft only; resets attestation) | `broadcast`, `recipients` (list of numbers or `{recipient, params, consent_source, consent_at}`), `csv_text` | `success`, `added`, `skipped`, `skipped_total`, `invalid`, `invalid_total` | `not_found`, `not_draft`, `csv_too_large`, `too_many_recipients`, `invalid_params`, `no_recipients` |
| `attest_broadcast_consent` | write | `broadcast`, `consent_source` | `success`, `broadcast`, `consent_attested`, `consent_source` | `not_found`, `invalid_state`, `consent_source_required` |
| `remove_broadcast_recipient` | write (Draft only; resets attestation) | `broadcast`, `recipient` (number or row name) | `success`, `broadcast`, `removed`, `queued` | `not_draft`, `invalid_recipient`, `not_found` |
| `delete_broadcast` | write (Draft only) | `broadcast` | `success`, `broadcast`, `deleted` | `not_draft`, `not_deletable` |
| `preview_broadcast` (POST: it stores the cost estimate) | write | `broadcast` | `success`, `broadcast`, `status`, `consent_attested`, `limits` (with `warnings`, `blocking`, `limits_in_effect`; section 6), `limits_in_effect`, `cost`, `confirm_required` (true when `require_typed_count` is on and something is queued), `queued` | `not_found` |
| `start_broadcast` | write (Draft only) | `broadcast`, `confirm_count`, `override_warnings` (JSON list of warning codes) | `success`, `broadcast`, `status` (`Running`), `queued`, `deferred_over_budget` | `not_found`, `invalid_override_warnings`, `no_recipients`, `confirm_mismatch`, the code of the first blocking issue (section 6), `consent_not_attested`, `another_broadcast_running`, `warnings_changed` (with the current `warnings`); refusals by the runner carry `blocking` or `warnings` in the response. Wrong state and permission failures are raised as errors |
| `pause_broadcast` | write | `broadcast` | `success`, `broadcast`, `status` | `not_found` |
| `resume_broadcast` | write (Paused only) | `broadcast` | `success`, `broadcast`, `status`, `queued` | `not_found`; runner refusals are raised as validation errors (blocking issues, consent, another broadcast running); no warning acknowledgement is needed |
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
- Registry rows flagged "Not verified against Meta's documentation": BSUID refusal, US `+1` marketing non-delivery, copy-code length 15, Huf's own location text (1000) and link suffix (2000) caps.
- What Meta does when a broadcast is resumed with more recipients than the remaining 24-hour budget (Huf's over-budget deferral applies at start only).
- Whether the audience `events` purpose has a corresponding Meta template category (Huf records it; no category requires it).
- The audience purpose mapping (MARKETING needs `marketing`; UTILITY and AUTHENTICATION need `utility`) is Huf's policy over Meta's opt-in rule, not a Meta requirement.

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
- **One Running broadcast per gateway** by default (`one_active_per_gateway`, a safety). Switching it off has no shared speed budget between broadcasts; that coordination is not implemented.
- **135000 pauses conservatively** (section 11).
- **Tier unknown means no budget check** (warning `tier_unknown`).
- **Resume does not defer over-budget rows.** Only `start_broadcast` applies the deferral; a resumed broadcast is not checked against the budget as a block or a warning to acknowledge.
- **Per-broadcast defaults mask two settings (needs a live check).** The `WhatsApp Broadcast` doctype defaults `max_recipients` to 1000 and `mps` to 10. `policy.resolve` treats any positive per-broadcast value as the broadcast's own and ranks it above settings, so for broadcasts created through `create_broadcast` without those arguments, changing `max_recipients_default` or `default_mps` may have no effect, and the sending speed would stay at 10 per second rather than `default_mps`'s 20. Not confirmed on a running site.
- **Audience snapshot.** Rows are copied when the audiences are picked (not at start); later list edits do not reach a Draft until the picks are set again.
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

## 14. Limits you can see and change

**Rule.** If Meta imposes it, Huf shows it read-only with the reason. If Huf adds it, it is a setting (or a safety, or a documented internal constant) with a default, a range and a note. Effective value = the broadcast's own value (only for `max_recipients_default`, via the broadcast's `max_recipients`, and `default_mps`, via its `mps`), then **WhatsApp Broadcast Settings**, then the default. A blank setting uses the default. The registry is `broadcast/policy.py`; [BROADCAST_LIMITS.md](BROADCAST_LIMITS.md) is generated from it (a test fails when the two drift) and lists every key, default, range and note. That table is the reference for numbers; this document does not repeat them.

Where to see and change them: the **Settings** tab of the WhatsApp page, section **Broadcast limits** (one row per limit: effective value, default, who sets it, note, an input and reset for editable rows). Who can change them: System Manager or Huf Admin. The wizard's Preview step lists "Limits applied to this broadcast".

### Kinds and groups

| Kind | Meaning |
|---|---|
| `meta` | Set by Meta. Read-only, shown with the reason. Rows flagged "Not verified against Meta's documentation" in the table come from track research or Huf's own reading and were not confirmed. |
| `setting` | A Huf limit an operator may change. |
| `safety` | A Huf safety net, on by default, editable. |
| `internal` | A Huf engine constant. Read-only, shown for transparency. |

Groups (`group` in the API): `meta` (what Meta enforces), `recipients` (list sizes, CSV size, phone digits), `speed` (sending rate, batches, attempts, wait times), `quality` (slowing down while Meta holds messages), `safety` (one running broadcast per gateway, internal engine timing), `confirmation` (typed count, consent attestation), `api` (calls per minute per endpoint), `audiences` (audience and import sizes).

### What changed from earlier versions

Registry defaults equal the earlier hard-coded values, so nothing changes until someone edits a setting. Two behaviours changed on purpose:

- **Number quality RED is a warning**, not a block. The operator must acknowledge it at start.
- **Going over the 24-hour budget is a warning**, not a block. Continuing sends what fits and holds the rest (below).

Blocking and warning entries are now coded objects `{code, message, limit_key}` instead of strings. The earlier per-broadcast limits (1000 default, 10000 highest) are the settings `max_recipients_default` and `max_recipients_ceiling`, where `0` means no limit.

### Warnings and the override flow

1. `preview_broadcast` returns `warnings` and `blocking` (section 6). Blocking issues cannot be overridden.
2. The wizard shows each warning with an "I understand, continue anyway" checkbox; Next stays disabled on the Preview step while a warning is unchecked or a blocking issue exists.
3. `start_broadcast` takes `override_warnings`, the list of warning codes the caller acknowledged. The server recomputes the preview. If the current set of warning codes is not exactly the acknowledged set (a warning appeared, or one went away), the start is refused with error `warnings_changed` and the current `warnings`; review them and call again. An empty list acknowledges "no warnings".
4. Callers authenticated with an API key (`Authorization: token key:secret`) skip the typed count, but still have to pass `override_warnings` explicitly, and it must match.
5. Consent and "one running broadcast per gateway" are enforced in one place, `runner.start` under a lock on the Gateway row; the preview only reports them.
6. The acknowledged codes go into the audit log line and the comment on the broadcast.

**Over-budget deferral.** If `over_budget` is acknowledged and the tier is known, the first `remaining_24h` queued rows (oldest first) are sent. The rest keep status `queued` (no new status) with `next_attempt_at` set to 24 hours after the start (a rolling window, not a fixed clock time). The runner sends only rows that are due, so the tick goes idle and the `*/5` cron revives it; held rows go out once due. `start_broadcast` returns `deferred_over_budget`. Meta's own tier limit still applies to what is actually sent. `resume_broadcast` does not apply this deferral.

### Typed count

`require_typed_count` (safety, on): the wizard asks for the queued recipient count, and `start_broadcast` requires `confirm_count` equal to `queued + deferred` (`confirm_mismatch`). It is skipped for API-key callers. Turning the setting off removes the check for everyone. The preview's `confirm_required` reports the current state.

### API: `get_broadcast_limits`

`huf.ai.whatsapp.broadcast.api_limits.get_broadcast_limits(broadcast=None)`, GET. Without `broadcast` it needs Gateway read permission (or Huf Admin); with `broadcast`, read permission on that broadcast's Gateway. A failed Meta read does not raise. Returns `{"success": true, "limits": [row, ...]}`; each row has:

`key`, `label`, `group`, `kind` (`meta` | `setting` | `safety` | `internal`), `value` (what is stored; null when blank or not editable), `default`, `effective`, `source` (`default` | `settings` | `broadcast`), `unit`, `min`, `max`, `note`, `editable`.

- For `max_recipients_default` and `max_recipients_ceiling`, a stored `0` means no limit: `value` is `0` and `effective` is null.
- The rows `messaging_tier_24h` and `quality_rating` are filled only when `broadcast` is given: `value` and `effective` are the live tier maximum and quality from Meta, plus `as_of` (ISO time of the read; Meta reads are cached for `limits_cache_ttl_seconds`, 600 s). The tier row also carries `tier`. Without `broadcast` they are null.
- With `broadcast`, `source` is `broadcast` for `max_recipients_default` and `default_mps` when that broadcast carries its own value.

### API: `update_broadcast_limits`

`huf.ai.whatsapp.broadcast.api_limits.update_broadcast_limits(values)`, POST, System Manager or Huf Admin. `values` is a JSON object (string or dict) of `key: value`; `null` or an empty string resets that key to its default.

- Only `setting` and `safety` rows can be changed; unknown or read-only keys are refused.
- Numbers must be whole numbers inside the row's `min` and `max` (the one ratio, `held_ratio_limit`, may be fractional). Booleans accept true/false, 1/0, on/off, yes/no.
- `max_recipients_default` and `max_recipients_ceiling` also accept `0` (no limit).
- Cross-field rules: `max_recipients_default` cannot exceed `max_recipients_ceiling`, `ramp_first_batch` cannot exceed `max_batch`, `min_held_sample` cannot exceed `held_window`.
- Nothing is stored if any value is invalid. Errors: `invalid_params` (not a non-empty object), `invalid_limit` (the message names the key).
- Each call writes a log line and a comment on the settings record (`limits changed by <user>: key=value`).
- Returns `success` and the `limits` rows, same shape as the get call. `get` and `update` are themselves rate limited (`rate_limits_read`, `rate_limits_write`).

### What each group means

- **Recipients**: the broadcast's default and highest recipient cap, stored rows per broadcast, recipients per request, CSV size, shortest phone number. They govern the intake in section 2.
- **Speed**: default speed, speed cap (a setting can only lower what Meta reports), first and largest batch, attempts per recipient, wait after a token error, wait when the gateway is down (sections 5 and 7).
- **Quality**: slow down while Meta holds messages, with the held ratio, window and minimum sample that trigger it.
- **Safety**: one running broadcast per gateway. Switching it off lets broadcasts run side by side; speed is not shared, so each runs at its own rate, and every start then shows the warning `other_broadcast_running`.
- **Confirmation**: type the count to start; require consent confirmation. Meta requires opt-in either way; with the second box off, Huf stops asking for the record (this includes audience creation, section 15).
- **API**: calls per minute for each broadcast, limits and audience endpoint.
- **Audiences**: contacts per audience, inline import size, contacts per import, audience CSV size, tags per contact, tag length, name length, contacts removed per request, page size, audiences per broadcast.
- **Internal (read-only)**: tick timeout and budget, lock lifetime, heartbeat, permission re-check, stuck-sending timeout, Meta cache lifetime, deadlock retries, location text and link suffix lengths, the number of skipped rows echoed back, import chunk sizes.

Not verified: that every non-Meta gate in `outbound_policy.check_template` / template-outreach checks (reached through the bridge send, section 4) is classified in the registry. The registry lists the template-approved rule; other bridge refusals are described in section 7 and were not individually classified as Meta's or Huf's.

## 15. Audiences

An audience is a saved, consented list of contacts that belongs to one Gateway. Consent lives with the list; opt-out lives with the contact and the sender number. A broadcast can pick audiences instead of (or as well as) pasted numbers.

### Consent per list

`WhatsApp Audience` fields: `gateway`, `title`, `description`, `consent_source` (required text: where the opt-in was collected), `consent_basis` (required: `opt-in form`, `checkout`, `in-store`, `inbound message`, `import with attestation`), purposes (`marketing`, `utility`, `events`; at least one), optional `default_consent_at`, `consent_attested_by` / `consent_attested_at`, `member_count`, `suppressed_count`, `is_adhoc`.

- **Attestation is set by the server** when the audience is created: the attester is the session user and the time is now. Clients cannot send it.
- `create_audience` requires `consent_attested` to be true when `require_consent_attestation` is on (`consent_not_attested`), and at least one purpose (`purposes_required`). `default_consent_at` (when the consent was collected) cannot be in the future; it can be earlier, and the attester is still recorded.
- **Immutable after create**: attester, attestation time, `default_consent_at`, `gateway`, `consent_basis`. Purposes can be narrowed but never widened; for a new purpose create a new audience. Editable: title, description, consent source text, and narrowing purposes.
- Purposes are Huf's own record of what the contacts agreed to. Meta's rule is the same for all of them: opt-in is needed for any business-initiated message.
- Per member, `consent_source` and `consent_at` can override the audience's. A broadcast row takes the member's `consent_source`, else the audience's; for the time, the member's `consent_at`, else the audience's `default_consent_at`, else the attestation time.

### Opt-out is per contact and sender number

Audiences never store opt-outs. They are read from the gateway's consent records (`gateway_consent`): a STOP reply puts the contact's entry on this gateway into the opted-out state (`opted_out`), and a marketing stop is the latest `marketing_messages` consent value `stop` (`marketing_opted_out`). Members stay in their lists and show the suppression reason; counts report them separately; they are stored as `skipped` when rows are written (section 2) and checked again before each send (section 4). Consent records are per gateway, so a contact who stopped on one sender number is not suppressed on another gateway. Member lists and audience counts check the marketing stop whatever the template; a broadcast selection checks it only for MARKETING templates.

### Purpose check: preview and start

A template category needs a purpose on every included audience: `MARKETING` needs `marketing`; `UTILITY` and `AUTHENTICATION` need `utility`. `events` is recorded but no category requires it. An unknown category skips the check. The check runs:

- in `set_broadcast_audiences` and the selection previews: an audience without the purpose is listed in `blocked` and adds no rows;
- in `preview_broadcast`: blocking issue `audience_purpose_mismatch`, one per offending audience;
- again inside `start_broadcast` and `resume_broadcast`, because both run the preview.

The category is read from the template record each time, not from the snapshot taken when the broadcast was created, because Meta can recategorize a template after approval. Excluded audiences are not checked.

### Selection: include, exclude, dedupe, tags

A selection is a list of `{audience, tag_filter_mode: "any"|"all", tags: [], exclude: false}`.

- At least one include; every audience must belong to the broadcast's gateway; at most `audience_max_selection_items` picks.
- **Tag filters** per pick: `any` (member has at least one listed tag) or `all` (has every listed tag). Tags are lower-cased, whitespace-collapsed and deduped. No tags means everyone in the list.
- **Exclude**: recipients matched by an exclude pick (with its own tag filter) are removed from the includes.
- **Dedupe, first list wins**: the first included list that holds a recipient supplies its params and consent; later copies are counted as duplicates. Picks are processed in order.
- Counts returned: `total` (matched in include lists), `excluded`, `dupes`, `blocked_by_purpose`, `suppressed`, `final` (rows that can be sent). `total = excluded + dupes + blocked_by_purpose + rows`; `suppressed` is part of `rows`; `final = rows - suppressed`. `per_audience` gives `matched` and `added` for each pick.

### Wiring into a broadcast

`set_broadcast_audiences(broadcast, selection)` (Draft only) stores the picks in the broadcast's `audiences` table and writes the rows through the same intake as a manual add (section 2), so every filter and cap applies there. The rows are a **snapshot**: later edits to a list do not change the broadcast; pick again to refresh. Picking again replaces only rows that came from audiences; manually added rows are kept. Each row stores its `audience`. The response has `counts`, `per_audience`, `blocked`, `replaced`, `added`, `skipped`, `invalid` (with totals), `queued` and `consent`.

Consent: changing the picks resets an existing broadcast attestation. When `require_consent_attestation` is on, every sendable row comes from an audience with a recorded attester and there are no manual rows, the audiences satisfy the broadcast's consent requirement: the broadcast is marked attested by the caller, with `consent_source` `Audiences: <titles>`. `consent.satisfied`, `consent.manual_rows` and `consent.audiences` in the response explain the state. If manual rows exist, the broadcast's own attestation is still required.

### Ad-hoc lists

`create_audience(..., is_adhoc=true)` makes a list that is hidden from the library (`list_audiences` omits it unless `include_adhoc`). It needs the same consent source, basis, purposes and attestation as any other list. It exists for "paste or upload numbers for this broadcast only".

### Import

`import_members(audience, csv_text | rows, mapping, on_conflict)`; send text or rows, not both.

- **Columns**: `mapping` is `{"phone", "name", "tags", "consent_source", "consent_at", "params": [col, ...]}` using CSV header names (or row keys). Without a mapping the headers are detected: phone (`phone`, `recipient`, `phone_number`, `mobile`, `wa_id`, `whatsapp`, `number`), name (`name`, `display_name`, `full_name`, `contact`, `customer`), tags (`tags`, `tag`, `segment`, `segments`, `labels`; separated by `,`, `;` or `|`), `consent_source`, `consent_at` (`consent_at`, `consent_date`, `consented_at`). `params` columns are only used when named in `mapping`; they become the body values, in order.
- **Examples.** A file like

```csv
phone,name,tags,consent_at
15551230001,Asha,vip;newsletter,2026-09-01
15551230002,Ben,newsletter,
```

  imports with no `mapping`. To carry the name as the first template variable, also pass `mapping={"phone": "phone", "params": ["name"]}`. Rows can also be sent as JSON: `rows=[{"phone": "15551230001", "name": "Asha", "tags": "vip"}]`.
- **Conflicts** (`on_conflict`): `skip` keeps existing contacts, `update` overwrites the fields provided and merges tags, `fail` writes nothing if any contact already exists (error `conflicts` with the first 50).
- **Inline or background**: up to `audience_inline_import_rows` rows run in the request and return totals. Larger imports run as a background job (queue `long`, timeout 3600 s) and return `{queued: true, job_id, rows}`. Poll `get_import_status(job_id, audience)`; progress is also published as the realtime event `wa_audience_import_progress` to the importing user. Progress is kept for `audience_import_job_ttl`; after that, or if the cache is cleared, the status call answers `not_found`.
- **Results**: `added`, `updated`, and exact `invalid_total` / `skipped_total` with example lists `{row, recipient, reason}` capped at 200. Invalid reasons: `invalid_number`, `bsuid_not_supported`, `name_too_long`, `invalid_tags`, `invalid_params`, `invalid_consent_date`, `consent_date_in_future`. Skipped reasons: `duplicate_in_file`, `already_in_audience`, `audience_full`.
- Sizes (contacts per import, CSV MB, contacts per audience, tags per contact, tag and name length) are the `audience_*` settings; the shortest phone number setting also applies.

### Masking

Callers with read but not write permission on the gateway see phone numbers as the last four digits: in `list_members` (the response has `masked: true`) and in import example lists. `get_audience` returns `can_see_numbers`. Full numbers need Gateway write.

### Delete, rename, edit

- Delete (`delete_audience`) and rename (a new title through `update_audience`) are refused while a broadcast in `Draft`, `Queued`, `Running` or `Paused` uses the audience (`audience_in_use` for delete; the generic `invalid` error for rename). Finished broadcasts keep the audience name on their rows.
- Deleting an audience deletes its members.
- Members can be changed only through the audience API; direct REST or desk edits are refused.

### Wizard flow

The **Audiences** tab of the WhatsApp page lists audiences, creates them with the consent form, imports with column mapping, and shows members with tag and suppressed filters. The broadcast wizard in the code this document was written from still has the steps Template, Recipients, Consent, Preview, Confirm. A step that picks audiences (per-list tags, include/exclude, live counts total / duplicates / suppressed / final, and "paste or upload for this broadcast only" creating an ad-hoc audience) is separate work (WP-E2) and is not described here as shipped.

### Audience API reference

Reads need read permission on the audience's Gateway; writes need write permission (or the integrations-manage capability). Methods are in `huf.ai.whatsapp.broadcast.audiences.api` unless noted. Rate limits (per minute, settings): reads 240, writes 60, imports 20.

| Method | HTTP | Needs | Parameters | Returns | Error codes |
|---|---|---|---|---|---|
| `create_audience` | POST | write | `gateway`, `title`, `consent_source`, `consent_basis`, `consent_purposes`, `consent_attested`, `description`, `default_consent_at`, `is_adhoc` | `success`, `audience` | `gateway_required`, `purposes_required`, `consent_not_attested`, `invalid` |
| `update_audience` | POST | write | `audience`, `title`, `description`, `consent_source`, `consent_purposes` (narrow only) | `success`, `audience` | `not_found`, `purposes_required`, `invalid` |
| `delete_audience` | POST | write | `audience` | `success` | `not_found`, `audience_in_use` |
| `list_audiences` | GET | read | `gateway`, `search`, `include_adhoc`, `start`, `limit` (at most `audience_page_size_max`) | `success`, `audiences`, `total` | `gateway_required` |
| `get_audience` | GET | read | `audience` | `success`, `audience` (with `tags` counts, `used_by`, `can_see_numbers`) | `not_found` |
| `import_members` | POST | write | `audience`, `csv_text` or `rows`, `mapping`, `on_conflict` | inline: `success`, `queued: false`, `added`, `updated`, `invalid`, `skipped` (+ totals), `member_count`, `suppressed_count`; background: `queued: true`, `job_id`, `rows` | `not_found`, `invalid`, `no_rows`, `csv_too_large`, `too_many`, `unknown_column`, `mapping_missing_phone`, `conflicts` |
| `get_import_status` | GET | read | `job_id`, `audience` | `success`, `status` (`queued`, `running`, `done`, `failed`), `processed`, `total`, `result`, example lists | `not_found` |
| `remove_members` | POST | write | `audience`, `recipients` (at most `audience_max_remove_per_request`) | `success`, `removed`, counts | `not_found`, `too_many`, `invalid` |
| `list_members` | GET | read | `audience`, `search`, `tags`, `tag_mode`, `suppressed`, `start`, `limit` | `success`, `members` (each with `suppressed` reason or null), `total`, `masked` | `not_found` |
| `preview_audience_selection` | GET | read on the broadcast's gateway | `broadcast`, `selection` | `success`, `counts`, `per_audience`, `blocked`, `category`, `purpose_required` | `not_found`, `invalid` |
| `preview_audience_selection_for_gateway` | GET | read | `gateway`, `selection`, `template_category` (omit to skip the purpose rule) | same as above | `gateway_required`, `invalid` |
| `set_broadcast_audiences` (module `audiences.wiring`) | POST | write on the broadcast's gateway | `broadcast`, `selection` | see "Wiring into a broadcast" | `not_found`, `not_draft`, `invalid`, `busy_retry` |
| `get_broadcast_audiences` (module `audiences.wiring`) | GET | read | `broadcast` | `success`, `selection`, `consent` | `not_found` |

Failures return `{"success": false, "error": <code>, "message": ...}`; a missing permission raises a permission error. Mutating calls write an audit line (`huf.whatsapp.audience`) and a comment on the audience.

## 16. Meta references

- Send messages: <https://developers.facebook.com/documentation/business-messaging/whatsapp/messages/send-messages>
- Messaging limits: <https://developers.facebook.com/documentation/business-messaging/whatsapp/messaging-limits>
- Throughput: <https://developers.facebook.com/documentation/business-messaging/whatsapp/throughput>
- Template pacing: <https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/template-pacing>
- Status webhook: <https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/reference/messages/status>
- Pricing: <https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing>
- Error codes: <https://developers.facebook.com/docs/whatsapp/cloud-api/support/error-codes>
