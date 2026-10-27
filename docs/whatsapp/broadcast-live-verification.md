# WhatsApp Broadcast: live verification plan

Plan for checking the broadcast feature on a real WhatsApp Business number before it is used for anything else. Read [BROADCAST.md](BROADCAST.md) first. This document is a plan. The scenarios below have not been run yet.

## 1. Rules for the run

- **Test number only.** Use a Meta test or sandbox number on a non-production gateway. Do not use the production number that serves customers.
- **Allow-listed recipients only.** Recipients are the operator's own numbers, listed in advance in the run notes, each of which has opted in. No other number may be added, including by CSV.
- **No real customer data.** Recipient rows and parameters use the test names only.
- **Approved template.** Use a test template that is `APPROVED` in WhatsApp Manager. Note its category (utility for most scenarios; marketing only for the marketing-specific checks, and only to allow-listed numbers that are not US `+1`, because US `+1` marketing is not delivered).
- **Owner-only steps.** Anything that changes account settings, creates standing rules, accepts Meta terms, or enables Marketing Messages API is done by the account owner, not by the operator running this plan.
- **No credentials in evidence.** Do not paste tokens, App Secrets, or phone-number IDs into screenshots or logs. Redact the `Authorization` header and the `phone_number_id` before saving.

## 2. Environment preconditions

| Check | Expected |
|---|---|
| Gateway health | `healthy` or `degraded` with no blocking reasons |
| Connection state | `Connected` |
| Token check (`check_token` with `force`) | Valid, no `access_token_invalid` |
| Webhook subscription | `messages` and `message_template_status_update` subscribed |
| Messaging limit | Readable via `broadcast_limits`, or the preview warns it is unknown (record which) |
| One active broadcast | No other broadcast `Running` on the gateway |
| Kill switch | Tested first, see scenario S7 |

## 3. Scenarios

Each scenario lists the setup, the steps, what to expect, and the evidence to keep.

### S1. Happy path, small list

- Setup: 3 allow-listed recipients, approved utility template, consent attested with source `test-run`.
- Steps: create draft, add 3 recipients, attest consent, preview, start with `confirm_count=3`, wait for `Completed`.
- Expect: 3 rows reach `sent`, then `delivered` and `read` as the handsets report. Counters match the rows. `finished_at` is set.
- Evidence: broadcast detail screenshot, recipient table export, Meta message log entries for the three wamids.

### S2. Preview blocks and warnings

- Setup: one allow-listed recipient that has a STOP recorded in Gateway Consent, one duplicate, one invalid number.
- Expect: the STOP row is `skipped` with reason `opted_out`; the duplicate is removed; the invalid number is reported as `invalid`. Start with the wrong `confirm_count` is refused.
- Evidence: preview JSON, refusal message.

### S3. Template not approved

- Setup: a template that is `PENDING` or `REJECTED` (use an existing one on the test account).
- Expect: preview shows it in `blocking`; start is refused. No row is sent.
- Evidence: preview JSON, refusal message, Meta message log showing no new sends.

### S4. Held message

- Setup: a template that is new or recently paused, so Meta may hold messages for quality assessment.
- Steps: start a small broadcast and record `message_status` for each send response.
- Expect: rows show `message_status = held_for_quality_assessment` where Meta returns it. Held ratio above 30% slows the runner. Replay of the held status webhook (fixture `broadcast_status_held.json`) moves a row to `sent` and then no further, since the fixture is a `sent` status for a held message.
- Evidence: send response fields for each row, runner log lines showing throttling.

### S5. Failed send, permanent error

- Setup: one recipient with a number not on WhatsApp (test number from Meta docs that fails), in the allow-list for this scenario only.
- Expect: row becomes `failed` with the error code stored. No retry.
- Evidence: row with `error_code`, `error_message`, `failed_at`.

### S6. Pause signals

- Setup: a test template; a signed replay of a `failed` status with code 135000 (`broadcast_status_failed_135000.json`) for an in-flight wamid.
- Expect: broadcast moves to `Paused` with reason naming 135000. Queued rows remain `queued`. No new sends until resume.
- Evidence: broadcast `pause_reason`, audit comment, runner log.

### S7. Kill switch

- Setup: a running broadcast with queued rows.
- Steps: call `pause_all_broadcasts(gateway)`.
- Expect: the running broadcast pauses. Confirm no POST to `/messages` for queued rows after the pause (check the Meta message log timestamps and the runner log).
- Evidence: audit comment, log lines, timestamps.

### S8. Restart and claim safety

- Setup: a running broadcast with at least 10 queued rows, paced slowly.
- Steps: restart the worker during the run. Then start the runner again through resume.
- Expect: every row sent once. No `wamid` appears twice in the Meta message log for the same recipient. A row stuck in `sending` for more than 10 minutes becomes `unknown` and is not resent.
- Evidence: Meta message log for the test number, recipient table, `unknown` rows if any.

### S9. Unknown row handling

- Setup: simulate an ambiguous network error after the request (test environment only, with a forced timeout in the send path).
- Expect: row is `unknown`. Recovery does not resend it.
- Evidence: row state history, Meta message log showing at most one send for that recipient.

### S10. Cancel

- Setup: a paused broadcast with queued rows.
- Expect: cancel moves queued rows to `skipped` with reason `cancelled`. Already `sent` rows are unchanged.
- Evidence: counts before and after.

## 4. Signed webhook replay plan

Status webhooks are replayed against the test gateway's webhook endpoint to check ingest, monotonic status, and dedupe without waiting for Meta.

- Source fixtures: `huf/ai/whatsapp/tests/fixtures/broadcast_status_held.json`, `broadcast_status_failed_135000.json`, `broadcast_status_failed_131049.json`, `broadcast_status_failed_131050.json`. Copies of `status_sent.json`, `status_failed.json`, and so on are used for the other statuses.
- Signing: the body is signed with the gateway's App Secret using the same method as Meta (`X-Hub-Signature-256`). The App Secret is read from the gateway in the operator's shell, never written to a file in the repo.
- Steps:
  1. Replay each fixture once. Expect the matching row to update.
  2. Replay the same fixture again. Expect no second change (dedupe on `(wamid, status)`).
  3. Replay a `delivered` after a `read` for the same wamid. Expect the row to stay `read`.
  4. Replay `failed` for a row already `delivered`. Expect no change.
  5. Replay with a bad signature. Expect rejection and a `signature_failed` marker.
- Replay is done only against the test gateway. Replayed payloads use test wamids from the fixtures, not real ones. The replay must not run against the production webhook URL.
- Evidence: the HTTP status for each replay, the row state before and after, and the gateway event rows.

## 5. Evidence to capture

For each scenario:

- Date and time (UTC), operator name, and gateway name (the name only).
- Broadcast name and template name.
- The row states before and after, as a table.
- Meta message log entries for the test number (phone numbers masked).
- Log lines from the runner for the scenario window.
- Screenshots of the broadcast detail, with secrets and numbers masked.
- Any deviation from the expected result, with the cause if known.

Store evidence outside the repository. Do not commit it.

## 6. Revert checklist

Run after the last scenario, or immediately if a scenario causes unexpected sends.

- [ ] Kill switch: `pause_all_broadcasts(gateway)`. Confirm no running broadcasts.
- [ ] Cancel any draft or paused broadcast left from the run.
- [ ] Remove the test recipients from any list used outside this run.
- [ ] Confirm the feature flag or permission used to open the broadcast tab is back to its previous setting (owner-only).
- [ ] Confirm the scheduler job `resume_stale` has no running broadcasts to re-enqueue.
- [ ] Remove the test gateway's webhook subscription to `user_preferences` if it was added for the run (owner-only).
- [ ] Rotate the test App Secret if it was displayed during the run.
- [ ] Confirm the production gateway was not touched: no broadcast rows reference it.
- [ ] Record the revert time and who ran it in the evidence folder.

## 7. Owner-only steps

These are not done by the operator running the plan:

- Accepting Meta terms, including the Marketing Messages API terms.
- Changing the template category or the messaging-limit tier.
- Changing gateway permissions or the webhook subscription.
- Enabling any production gateway for broadcasts.
- Deciding whether a run may use marketing templates to real recipients.
