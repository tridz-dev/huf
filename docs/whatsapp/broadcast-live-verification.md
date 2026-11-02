# WhatsApp Broadcast: live verification plan

Plan for checking the broadcast feature on a real WhatsApp Business number before it is used for anything else. Read [BROADCAST.md](BROADCAST.md) first; it describes what each scenario should observe. This document is a plan. The scenarios have not been run yet.

## 1. Rules for the run

- **Test number only.** Use a Meta test or sandbox number on a non-production gateway. Do not use the production number that serves customers.
- **Allow-listed recipients only.** Recipients are the operator's own numbers, listed in advance in the run notes, each of which has opted in. No other number may be added, including by CSV.
- **No real customer data.** Recipient rows and parameters use test names only.
- **Approved template.** Use a test template that is `APPROVED` in WhatsApp Manager. Note its category. Use a utility template for most scenarios. Use a marketing template only for the marketing checks, and only to allow-listed numbers that do not start with `+1` (those are skipped for marketing, see BROADCAST.md section 12).
- **Owner-only steps.** Anything that changes account settings, creates standing rules, accepts Meta terms, enables the Marketing Messages API, or edits a template's status in WhatsApp Manager is done by the account owner, not by the operator running this plan.
- **No credentials in evidence.** Do not paste tokens, App Secrets, or phone-number IDs into screenshots or logs. Redact the `Authorization` header and the `phone_number_id` before saving.

## 2. Environment preconditions

| Check | Expected |
|---|---|
| Gateway health | `healthy` or `degraded` with no blocking reasons (an operator check; broadcast start does not read it) |
| Connection state | `Connected`. A disconnected gateway makes sends defer and pauses the broadcast. |
| Token check (`check_token` with `force`) | Valid, no `access_token_invalid` |
| Webhook subscription | `messages`, `message_template_status_update` and `user_preferences` subscribed (S2 and S6 need them) |
| Messaging limit | Readable (tier shown in preview), or the preview warns that it is unknown (record which) |
| One active broadcast | No other broadcast `Running` on the gateway |
| Kill switch | Tested first, see S7 |

## 3. Scenarios

Each scenario lists the setup, the steps, what to expect, and the evidence to keep.

### S1. Happy path, small list

- Setup: 3 allow-listed recipients, approved utility template, consent attested with source `test-run`.
- Steps: create draft, add 3 recipients, attest consent, preview, start with `confirm_count=3`, wait for `Completed`.
- Expect: 3 rows reach `sent`, then `delivered` and `read` as the handsets report. Counters match the rows. `finished_at` is set.
- Evidence: broadcast detail screenshot, recipient table export, Meta message log entries for the three wamids.

### S2. Intake filters and start guard

- Setup: one allow-listed number with a STOP recorded in Gateway Consent, one duplicate, one invalid number.
- Expect: the STOP row is stored `skipped` with reason `opted_out`; the duplicate is reported in `skipped` with reason `duplicate` and not stored; the invalid number is reported in `invalid` and not stored. Start with a wrong `confirm_count` returns `confirm_mismatch`. Start before attestation returns `consent_not_attested`. Adding recipients after attestation clears the attestation (attest again before start); adding to a non-Draft broadcast returns `not_draft`; `start_broadcast` on a `Paused` broadcast is refused (use `resume_broadcast`).
- Optional (marketing template): a number beginning with `1` and 11 digits is stored `skipped` with reason `us_plus_one_marketing`.
- Evidence: the add-recipients response, the recipient table, the refusal responses.

### S3. Template not approved

- Setup: create the draft and add recipients while the template is `APPROVED` (creating a draft with any other status is refused with `template_not_approved`). Then the account owner changes the template to a non-approved status in WhatsApp Manager.
- Steps: run preview, then try to start.
- Expect: preview `blocking` contains `template_not_approved:<STATUS>`; start is refused with `Broadcast blocked: ...`. No row is sent.
- Evidence: preview JSON, refusal message, Meta message log showing no new sends.

### S4. Held message

- Setup: a template that is new or recently paused, so Meta may hold messages for quality assessment.
- Steps: start a small broadcast and record `message_status` for each send response.
- Expect: rows show `message_status = held_for_quality_assessment` where Meta returns it. When at least 10 of the last 50 sent rows exist and more than 30% are held, the runner drops to a quarter of the rate and halves batches (visible in the pace of sends).
- Webhook replay: a replay of the fixture `broadcast_status_held.json` is a `sent` status. Run it against a row that is `queued`, `deferred` or `sending`; it moves the row to `sent` and no further. Against a row that is already `sent` or beyond it changes nothing. The fixture carries no held information; it only exercises the status path.
- Evidence: send response fields for each row, runner log lines.

### S5. Failed send, permanent error

- Setup: one recipient with a number not on WhatsApp (a test number from Meta docs that fails), in the allow-list for this scenario only.
- Expect: row becomes `failed` with `error_code`, `error_message` and `failed_at`. No retry.
- Evidence: the row.

### S6. Pause signals

- Setup: a running test broadcast with queued rows and a signed replay of `broadcast_status_failed_135000.json` for an in-flight row (see section 4 for editing the wamid and `biz_opaque_callback_data`).
- Expect: the row becomes `failed` with code 135000 and the broadcast moves to `Paused` with `pause_reason` "WhatsApp error 135000 (messages dropped by pacing)". Queued rows stay `queued`. No new sends until resume.
- Also check, with the account owner: pausing or disabling the test template in WhatsApp Manager (or a replayed `message_template_status_update` for it) pauses a Running broadcast that uses it, with reason `template:paused` or `template:disabled`.
- Evidence: `pause_reason`, audit comment, runner log.

### S7. Kill switch

- Setup: a running broadcast with queued rows.
- Steps: call `pause_all_broadcasts(gateway)`.
- Expect: the running broadcast pauses with reason `kill_switch`. Confirm no POST to `/messages` for queued rows after the pause (Meta message log timestamps and the runner log). Rows that were `sending` at that moment may still finish.
- Evidence: audit comment, log lines, timestamps.

### S8. Worker restart and claim safety

- Setup: a running broadcast with at least 10 queued rows, paced slowly (low `mps`).
- Steps: restart the worker during the run. Do not call resume (resume only works from `Paused`). Wait up to 5 minutes; the `*/5` cron (`resume_stale`) revives a Running broadcast that has no live tick. If the broadcast was `Paused`, use resume instead.
- Expect: every row is sent once. No recipient receives two messages and no `wamid` repeats in the Meta message log. A row left in `sending` for more than 10 minutes becomes `unknown` and is not resent.
- Evidence: Meta message log for the test number, recipient table, `unknown` rows if any.

### S9. Unknown row handling

- Setup: simulate an ambiguous network error after the request (test environment only, with a forced timeout in the send path).
- Expect: the row is `unknown`. Recovery does not resend it. A later `sent`, `delivered` or `read` webhook for it moves it forward (`sent` resolves `unknown`).
- Evidence: row state, Meta message log showing at most one send for that recipient.

### S10. Cancel

- Setup: a paused broadcast with queued rows.
- Expect: cancel sets `Cancelled` and moves `queued` and `deferred` rows to `skipped` with reason `cancelled`. Rows already `sent` are unchanged.
- Evidence: counts before and after.

### S11. Retry cap and 131049 terminal skip (test environment only)

- Setup: a forced retryable error (for example a stubbed 130429 response) on one row.
- Expect: the row is `deferred` with growing delays (about 2, 4, 8, 16 s) and is `failed` after the fifth POST attempt (`attempts = 5`). A stubbed 131049 (send response) gives `skipped` with `skip_reason` `per_user_marketing_limit` and `error_code` 131049; it is never claimed again and the broadcast can complete. `deferred` is still used for retryable errors (above) and gateway disconnect.
- Evidence: row `attempts`, `next_attempt_at`, `skip_reason`, error fields.

### S12. Marketing stop

- Setup: a `Paused` broadcast with an allow-listed contact queued, and a second `Draft` broadcast with the same contact queued. Replay a `user_preferences` marketing-stop event for the contact (needs the `user_preferences` subscription), or send STOP from the contact's handset.
- Expect: the contact's `queued` and `deferred` rows in `Queued`, `Running` or `Paused` broadcasts become `skipped` with reason `opted_out`. A row in a `Draft` broadcast is not changed by the event; it is skipped at send time instead (`marketing_opted_out` for a MARKETING template).
- Evidence: recipient rows before and after.

## 4. Signed webhook replay plan

Status webhooks are replayed against the test gateway's webhook endpoint to check ingest, monotonic status, and no-op replays without waiting for Meta.

- Source fixtures: `huf/ai/whatsapp/tests/fixtures/broadcast_status_held.json`, `broadcast_status_failed_135000.json`, `broadcast_status_failed_131049.json`, `broadcast_status_failed_131050.json`; plain `status_sent.json`, `status_delivered.json`, `status_read.json`, `status_failed.json` for the rest. The fixtures contain a placeholder `wamid` and `biz_opaque_callback_data` (`bcast-0001-r0001`). Edit the copy so that it holds the `wamid` or the recipient row name of a real test row on the target gateway (matching is scoped to broadcasts of the receiving gateway); the `metadata.phone_number_id` must be the test gateway's.
- Signing: the body is signed with the gateway's App Secret as `X-Hub-Signature-256: sha256=<hex HMAC-SHA256>`. Read the App Secret in the operator's shell; never write it to a file in the repo.
- Steps:
  1. Replay each fixture once against a row in an earlier state. Expect the row to update.
  2. Replay the same fixture again. Expect no second change (the rank cannot rise).
  3. Replay a `delivered` after a `read` for the same wamid. Expect the row to stay `read`.
  4. Replay `failed` for a row already `delivered`. Expect no change.
  5. Replay `broadcast_status_failed_131050.json`. Expect that row to become `failed` and a marketing stop to be recorded for the contact, which skips the contact's other `queued`/`deferred` rows in `Queued`, `Running` or `Paused` broadcasts of the gateway (`opted_out`).
  5a. Replay `broadcast_status_failed_131049.json`. Expect that row to become `skipped` (`per_user_marketing_limit`, `error_code` 131049), never resent.
  6. Replay with a bad signature. Expect rejection and a `signature_failed` marker in the health data.
- Replay is done only against the test gateway, with test rows. It must not run against the production webhook URL.
- Evidence: the HTTP status for each replay, the row state before and after, and the gateway event rows.

## 5. Evidence to capture

For each scenario:

- Date and time (UTC), operator name, and gateway name (the name only).
- Broadcast name and template name.
- The row states before and after, as a table.
- Meta message log entries for the test number (phone numbers masked).
- Log lines from the runner (`huf.whatsapp.broadcast` logger) for the scenario window.
- Screenshots of the broadcast detail, with secrets and numbers masked.
- Any deviation from the expected result, with the cause if known.

Store evidence outside the repository. Do not commit it.

## 6. Revert checklist

Run after the last scenario, or immediately if a scenario causes unexpected sends.

- [ ] Kill switch: `pause_all_broadcasts(gateway)`. Confirm no running broadcasts.
- [ ] Cancel any draft or paused broadcast left from the run.
- [ ] Remove the test recipients from any list used outside this run.
- [ ] Confirm the feature flag or permission used to open the broadcast tab is back to its previous setting (owner-only).
- [ ] Confirm no broadcast is `Running`, so the `resume_stale` cron has nothing to revive.
- [ ] Remove the test gateway's webhook subscription to `user_preferences` if it was added for the run (owner-only).
- [ ] Restore any template status changed for S3 or S6 (owner-only).
- [ ] Rotate the test App Secret if it was displayed during the run.
- [ ] Confirm the production gateway was not touched: no broadcast rows reference it.
- [ ] Record the revert time and who ran it in the evidence folder.

## 7. Owner-only steps

These are not done by the operator running the plan:

- Accepting Meta terms, including the Marketing Messages API terms.
- Changing the template category, template status or the messaging-limit tier.
- Changing gateway permissions or the webhook subscription.
- Enabling any production gateway for broadcasts.
- Deciding whether a run may use marketing templates to real recipients.

## Appendix: live UI with realtime and real webhooks (dev setup)

- **Realtime through a dev server.** socket.io must be reachable on the dev server's own port: proxy `/socket.io` (websocket) to the bench's socket.io port, send `X-Frappe-Site-Name: <site>` and `Host: <site>`, and rewrite `Origin` to `http://<site>` (socketio.js requires Origin's host to equal Host's host). In developer mode the realtime server authenticates by calling `http://<site>:<webserver_port>`, so that name must resolve inside the container (a one-line `dns.lookup` preload for that host when it is a `*.localhost` name). Inject `socketio_port` = the dev server port into the page boot.
- **Real status webhooks.** Meta sends them to the phone number's override (`GET /<PHONE_ID>?fields=webhook_configuration`). To point it at the broadcast bench: expose the bench with a tunnel that sends `Host: <site>`, set the Gateway's `app_secret` to the Meta app secret (signatures are verified; never disable that), then POST `webhook_configuration.override_callback_uri` + `verify_token` to the phone number. Record the previous value first and restore it afterwards.

