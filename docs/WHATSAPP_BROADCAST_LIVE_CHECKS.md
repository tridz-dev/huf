# WhatsApp broadcast: owner-live checks (remainder of S1-S12)

S1-S12 from [whatsapp/broadcast-live-verification.md](whatsapp/broadcast-live-verification.md) run as automated bench checks in `huf/ai/whatsapp/tests/test_broadcast_s1_s12.py` (Graph mocked, signed webhook replays through `handle_gateway_webhook`). Run that module first; it must pass. Only the parts below need a real Meta number and handset, and only the account owner does them. Four tests end in `skipTest("OWNER-LIVE: ...")` for these.

## Guard: allow-list the owner's phone only

Set the site config key `wa_outbound_allowlist` (enforced in `huf/ai/whatsapp/outbound_policy.py`, `check_allowlist`) to the owner's phone only, E.164 digits, before anything is started:

    bench --site <site> set-config wa_outbound_allowlist '["<owner digits>"]'

A key that is present but empty blocks every send; a missing key allows everything, so confirm it is set. Any other recipient is skipped with `recipient_not_allowlisted` (checked by S01 on the bench). Use the test gateway and an APPROVED UTILITY template. Remove the key afterwards only if the owner wants unrestricted sends.

## Checks

| Scenario | Steps (owner) | Expected evidence |
|---|---|---|
| S1 real receipts | Draft with the owner's number only, attest, preview, start with `confirm_count=1`. Watch the handset. | Row goes `sent`, `delivered`, `read` as the handset reports. Counters match. `finished_at` set. Screenshot of the broadcast detail and the Meta message log entry for the wamid. |
| S4 held message | Use a new or recently paused template. Start one send. | Row `message_status` is `held_for_quality_assessment` if Meta holds it (record the actual value either way). Send response fields from the runner log. |
| S5 permanent error | Add a Meta test number that fails (not on WhatsApp). Temporarily add that single number to the allow-list. | Row `failed` with `error_code`, `error_message`, `failed_at`, `attempts=1`; no retry. Then remove the number from the allow-list. |
| S8 worker restart | A broadcast with 10+ rows needs more recipients than the owner has, so use one number repeated through distinct recipient forms only if Meta accepts it; otherwise run with the owner's number alone and restart the worker between `sending` and `sent`. Wait 5 minutes for `resume_stale`. | One Meta message per recipient, no repeated wamid. A row left `sending` more than 10 minutes becomes `unknown`, not resent. |
| S3, S6 (template status) | In WhatsApp Manager, pause the test template (S6) or move it off APPROVED (S3). Restore it after. | S3: preview blocking `template_not_approved`, start refused. S6: running broadcast pauses with `template:paused`. Meta log shows no new sends. |

The webhook side of S4, S6, S9, S11 and S12 uses the bench replay; for a real run, point the Meta webhook at the test bench per the appendix of the verification plan and keep signature verification on.

## Evidence and revert

Keep evidence outside the repo with tokens, App Secret and phone-number id redacted. After the run: `pause_all_broadcasts(gateway)`, cancel leftovers, restore template status, rotate the App Secret if it was shown, and decide about the allow-list key. The full revert checklist is section 6 of the verification plan.
