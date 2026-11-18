# WhatsApp agent tools (generic, built in)

Huf ships six built-in agent tools so any app's agent can run audiences and broadcasts without writing its own.
They live in `huf/ai/tools/messaging/whatsapp_broadcast_tools.py`, are registered through the `huf_tools` hook and synced to
`Agent Tool Function` rows. Each one calls the same whitelisted functions the Huf UI uses
(`broadcast/api.py`, `broadcast/schedule.py`, `audiences/api.py`), as the signed-in user: Gateway write authority,
size caps, rate limits and opt-out policy all apply. No tool uses `ignore_permissions` or the externally-managed
audience API.

| Tool | Flags | What it does |
| --- | --- | --- |
| `whatsapp_list_templates` | read | Approved templates of a gateway with category and variable counts |
| `whatsapp_audience_upsert` | not outbound | Create an audience (gateway + title) or merge/replace members `{recipient, display_name, params, consent_source, consent_at}` |
| `whatsapp_broadcast_create` | not outbound | Draft from audience + template + params (optional SMS/email fallback) |
| `whatsapp_broadcast_start` | `is_outbound=1`, `confirmation_summary_path` | Start now, or schedule when `scheduled_at` is set |
| `whatsapp_broadcast_status` | read | Counts by status, masked failure sample, next scheduled broadcast |
| `whatsapp_broadcast_retry_failed` | not outbound | New Draft with the retryable failed recipients (never sends) |

All have `required_roles = "HUF Messaging Manager, System Manager"`. `HUF Messaging Manager` is created by
`create_huf_roles` (no desk access, never auto-granted); the user still needs Gateway permissions.
`send_otp` is never a tool (see `OTP_TOOL_DENYLIST`).

## Confirmation
Only `whatsapp_broadcast_start` sends, so only it is outbound. Every call parks on every run type with a card
showing the real queued recipient count, template, channel and audience(s) (`confirmation_summaries.whatsapp_broadcast_start`).
If the broadcast cannot be resolved or read, nothing is parked. The agent must pass `expected_recipient_count`;
if the queue changed between approval and execution the tool refuses with `recipient_count_changed`.

## Consent rule
No tool attests consent on behalf of a human. `whatsapp_broadcast_start` returns `consent_not_attested` unless the
broadcast was already attested (`attest_broadcast_consent` in the HUF broadcast screen with a consent source, or by
a human-attested audience). The result tells the agent to ask the user to attest in the HUF broadcast screen.
`whatsapp_audience_upsert` always sends `consent_attested=0`; when the site requires audience attestation, a human
creates the audience in the UI and the agent passes its name as `audience`.

## Using them from an external app
In the app's agent JSON (`<app>/huf/agents/*.json`), reference the tools by name next to the app's own tools:

```json
{"agent_name": "Messaging Assistant",
 "tools": ["whatsapp_list_templates", "whatsapp_audience_upsert", "whatsapp_broadcast_create",
           "whatsapp_broadcast_start", "whatsapp_broadcast_status", "whatsapp_broadcast_retry_failed",
           "customer_segment_members"]}
```

Re-seeding only tightens flags (`is_outbound`, `requires_confirmation`), so these settings cannot be loosened by an app.
