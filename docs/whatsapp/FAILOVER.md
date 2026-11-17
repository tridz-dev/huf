# WhatsApp broadcast failover (SMS / email)

When a WhatsApp broadcast send terminally fails, `huf/ai/whatsapp/broadcast/failover.py` can resend the message
as plain text over SMS then email.

## Configure
On the broadcast (or per recipient row, which overrides it):
- `fallback_channels`: ordered JSON list, e.g. `["sms","email"]`.
- `fallback_body`: **required** plain text. It is never derived from the template; without it nothing is sent.
- `fallback_body_kind`: set `"otp"` to refuse the email leg.
- `fallback_sms_gateway` / `fallback_email_gateway`: Gateway links (SMS defaults to Frappe SMS Settings, email to site mail).
- Recipient row only: `fallback_email` (the address for the email leg; the SMS leg uses the WhatsApp number).

## When it fires
Only from `status.apply_status` on a `failed` status with error code 131026, 131030 or 131021. Never for
sent-but-not-delivered timeouts, never for 131050 (user stopped marketing) or the per-user limit skip.

## Safety
- The recipient row is locked; a non-empty `fallback_attempts` is the claim, so duplicate or out-of-order webhooks fire at most one chain.
- A late WhatsApp delivered/read after a fallback is audited (`delivered_late`) and triggers nothing.
- `has_consent(channel, recipient, purpose)` is checked before each leg; a denied leg is skipped and audited.
- Email is refused for OTP-kind bodies.

## Audit
`fallback_attempts` (JSON list of `{channel, time, status, cost, ...}`) and `channel_delivered` (`whatsapp`, `sms` or `email`) on the recipient row.

## Reuse
`failover.run_chain(channels, phone=, email=, body=, body_kind=, sms_gateway=, email_gateway=)` returns `(attempts, delivered_channel)`.
