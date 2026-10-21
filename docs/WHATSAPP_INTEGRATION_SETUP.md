# WhatsApp Integration Setup (Meta Cloud API)

Huf connects to WhatsApp through the Meta WhatsApp Cloud API. Inbound messages arrive on a webhook; replies and agent-tool sends go out through the Graph API (single version constant `GRAPH_API_VERSION`, currently `v25.0`, in `huf/ai/gateway_adapters/whatsapp.py`).

## 1. What you need from Meta

Create a Meta app with the WhatsApp product and collect:

| Credential key | Where it comes from |
| --- | --- |
| `phone_number_id` | WhatsApp > API Setup (the phone number's ID, not the phone number itself) |
| `access_token` | A System User permanent token with `whatsapp_business_messaging` and `whatsapp_business_management` (temporary tokens expire in ~24h) |
| `webhook_verify_token` | A random string you choose; you enter the same value in Meta and in Huf |
| `app_secret` | App settings > Basic > App Secret. **Required**: every inbound POST is verified with `X-Hub-Signature-256` (HMAC-SHA256) and rejected without it |

Never commit these values to the repo.

## 2. Configure Huf

1. Create an **Integration Settings** record for service `whatsapp` and add the four credentials above (they are stored as encrypted Integration Credential rows).
2. Create a **Gateway** with provider `WhatsApp`, linked to that Integration Settings, and route it to your Agent.
3. **Enable the gateway** (`is_enabled`) before verifying the webhook in Meta. The GET verification handshake is accepted even while the gateway is disabled, but POST events are rejected with 403 until it is enabled, so enable it first to avoid losing early events.

## 3. Configure the Meta webhook

- Callback URL (must be public HTTPS, reachable by Meta; use a tunnel for local dev):
  `https://<your-host>/api/method/huf.ai.gateway_webhook.handle_gateway_webhook?gateway_name=<Gateway name>`
- Verify token: the `webhook_verify_token` value.
- Click Verify and Save, then **subscribe to the `messages` field** of the WhatsApp Business Account. Without that subscription no inbound messages are delivered.

Delivery/read status updates also arrive on this webhook; Huf acknowledges them with HTTP 200 and ignores them (no retry loop).

## 4. The 24-hour window and templates

WhatsApp only allows free-form text within 24 hours of the user's last inbound message. Outside that window, a send must use a Meta-approved **template** (agent tool action `send_template` with `template_name`, `language_code`, and an ordered list of body `parameters`). Free-form sends outside the window are rejected by Meta and surface as an error.

## 5. Agent tool credentials

The WhatsApp agent tool (`send_message`, `send_template`, `get_account_info`) resolves `phone_number_id` and `access_token` in this order: explicit tool arguments, the enabled WhatsApp Gateway's linked Integration Settings credentials (optionally pass `gateway` to pick one), then a `frappe_whatsapp` WhatsApp Account if installed. Text and template sends go through the same sender as gateway replies.

## 6. Optional: set up via Meta's WhatsApp Business Tools MCP

Meta hosts an MCP server at `https://mcp.facebook.com/whatsapp_business_tools` that can help with account, phone number and template management from an MCP client.

- Authentication is OAuth. Register your own Meta app and supply its pre-registered app (client) ID to your MCP client; dynamic client registration is not assumed.
- Add the server in your MCP client with that URL, complete the OAuth consent in the browser, and grant the requested WhatsApp Business permissions.
- Use it for convenience tasks (for example looking up the phone number ID or managing templates). The Huf webhook, `app_secret`, and verify-token steps above are still required; the MCP does not replace them.
- Treat the OAuth token as a secret and keep it out of the repository.

## Troubleshooting

- Verification fails: verify token mismatch, or the callback URL is not public HTTPS / missing `gateway_name`.
- Inbound POST returns 401: wrong or missing `app_secret`.
- Inbound POST returns 403: gateway not enabled.
- No messages arrive: the `messages` field is not subscribed.
- Send fails outside 24h: use a template.
