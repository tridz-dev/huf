# WhatsApp broadcast failover (SMS / email)

When a WhatsApp broadcast send terminally fails, `huf/ai/whatsapp/broadcast/failover.py` can resend the message
as plain text over SMS then email.

## Configure
On the broadcast (or per recipient row, which overrides it):
- `fallback_channels`: ordered JSON list, e.g. `["sms","email"]`.
- `fallback_body`: **required** plain text. It is never derived from the template; without it nothing is sent.
- `fallback_body_kind`: `marketing` (default; each channel needs an explicit marketing opt-in) or `transactional`.
  `otp` / `utility` are never accepted from broadcast authors; only `otp.py` passes `otp` to `run_chain` (refuses email).
- Set through `create_broadcast` / `update_broadcast` / `add_broadcast_recipients` (validated: channels are an ordered
  subset of sms,email; gateways must exist and be readable by the caller). Recipient rows copy the broadcast's values
  when added; `update_broadcast` re-copies them to queued rows; `retry_failed` copies them to the new Draft.
  A start is refused (`fallback_body_required`) when channels are set without a body.
- Audience members have no email column: put `fallback_email` in the member's `params`.
- `fallback_sms_gateway` / `fallback_email_gateway`: Gateway links (SMS defaults to Frappe SMS Settings, email to site mail).
- Recipient row only: `fallback_email` (the address for the email leg; the SMS leg uses the WhatsApp number).

## When it fires
Only from `status.apply_status` on a `failed` status with error code 131026, 131030 or 131021. Never for
sent-but-not-delivered timeouts, never for 131050 (user stopped marketing) or the per-user limit skip.

## Safety
- The recipient row is locked; a non-empty `fallback_attempts` is the claim, so duplicate or out-of-order webhooks fire at most one chain.
- The claim (`attempting`) is committed before any provider call and replaced with the result afterwards, so a lost write
  can never cause a second chain (worst case the audit stays `attempting`).
- Late-WA-delivered rule (owner decision): a WhatsApp `delivered`/`read` arriving after a fallback ran is audited
  (`delivered_late`) only. The fallback is not recalled; the customer may get both messages (inherent to failover).
- `has_consent(channel, recipient, purpose)` is checked before each leg; a denied leg is skipped and audited.
- Email is refused for OTP-kind bodies.
- Inbound STOP/START on verified SMS (twilio mode, valid signature) and email (webhook secret) update `Channel Consent`.

## Audit
`fallback_attempts` (JSON list of `{channel, time, status, cost, ...}`) and `channel_delivered` (`whatsapp`, `sms` or `email`) on the recipient row.

## Reuse
`failover.run_chain(channels, phone=, email=, body=, body_kind=, sms_gateway=, email_gateway=)` returns `(attempts, delivered_channel)`.
