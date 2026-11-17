# OTP delivery (`huf.ai.whatsapp.otp`)

Huf only delivers codes. It never generates or verifies them; verification stays in the calling app.

## Roles and scoping
- Callers need the `HUF OTP Sender` role (or System Manager).
- The caller must also have read permission on the Gateway document, for both `gateway` and `sms_gateway`
  (`gateway_forbidden` otherwise). Scope a sender to specific gateways with User Permissions on Gateway.
- `send_otp` and `get_otp_status` are not agent tools. They are denylisted (`OTP_TOOL_DENYLIST`) in the
  Agent Tool Function doctype and in app seeding.

## Request rules
- POST only. Send the code in the request body (form or JSON), never in the query string, because URLs end up in logs.
- Code: 4-15 letters or digits.

## Rate limits
Fixed windows (not sliding), counted in Redis with a TTL set on creation: 3 sends per phone per 10 minutes,
60 sends per caller per minute. Attempts that fail before Meta accepts them (validation, permission, opt-out,
template errors) are refunded. Attempts Meta accepted or rejected after receiving them are not.

## Idempotency
`idempotency_key` claims a 24h slot per caller, gateway, phone and key. A replay with the same code and template
returns the original message id (`replayed: true`) and sends nothing. A replay with a different code or template
returns `idempotency_conflict`. The slot is released on any failure so a retry can proceed.

## SMS fallback
- `fallback="sms"` only; email is never allowed. Requires `sms_gateway` and `fallback_text`.
- `fallback_text`: at most 480 characters, `{code}` exactly once, no links (`http`, `www`, `://`); else `invalid_fallback_text`.
- SMS gateway mode must be `twilio` or `send_only`. `frappe_sms` is refused with `sms_mode_not_allowed_for_otp`,
  because Frappe core `send_sms` stores the message (the code) in SMS Log.
- Fires synchronously only when WhatsApp refuses with `not_opted_in` or `window`.
- Consent rule: the SMS leg uses transactional (utility) consent and checks the SMS opt-out only. WhatsApp
  `not_opted_in` includes a WhatsApp opt-out, so a recipient who opted out of WhatsApp can still get the OTP by SMS
  if they have not opted out of SMS. This is intentional.
- `get_otp_status` also answers for SMS sends (`sent`, or `unknown` when the provider returns no id).

## No-logging guarantees
The code is never stored, logged, returned, or placed in error text. Errors and provider echoes are scrubbed, the
WhatsApp mirror row stores redacted parameters, and only a hash of the code is used for the idempotency fingerprint.
