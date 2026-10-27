# Microsoft Teams Gateway Operator Guide

Huf connects to Microsoft Teams through an Azure Bot (Bot Framework channel). Teams delivers
activities to the Huf webhook, and Huf replies through the Bot Framework connector. Behaviour is
taken from code; file references name the source of truth. Never put credentials in this document,
chat or logs.

Scope: single-tenant bots only. Managed identity (UserAssignedMSI), multi-tenant bots and sovereign
clouds (GCC, GCC High, DoD, 21Vianet) are not supported.

Status note: parts of this guide describe work that is still in progress on the Teams integration
track. Items marked **(planned)** are not available in every build yet. Items marked **(verify in your tenant)**
rely on Microsoft admin flows that Huf has not tested against a live tenant.

## 1. What the integration does

- Inbound: Teams sends Bot Framework activities to the Gateway webhook. Huf verifies the bearer token
  before any payload is normalized or stored.
- Conversation types: personal (1:1), group chat and team channel.
- Channels and group chats: the bot only sees messages that @mention it, unless the tenant grants
  the resource-specific consent "receive all messages" (RSC). The mention is stripped from the text
  before the agent sees it. Other mentions are kept.
- Threads: channel replies stay in the thread of the inbound message (`;messageid=` in the conversation id).
- Replies: sent from the stored conversation reference, using the service URL Teams sent with that conversation.
- Files: inbound file downloads in personal chat. Outbound file upload uses a consent card in personal chat only (see section 9).
- Adaptive Cards: not yet supported (see section 10).

## 2. Prerequisites

- A Huf site reachable over public HTTPS. Teams will not call a plain HTTP or private-IP endpoint.
- Permission to create an Azure Bot resource and an Entra (Azure AD) app in the tenant that will host the bot.
- Teams admin rights, or a tenant policy that allows custom app upload, to install the bot.
- A Huf user who can manage Gateways.

## 3. Create the Azure Bot (single-tenant)

Do this in the Azure portal (verify in your tenant: exact menu names change over time).

1. Create a **Azure Bot** resource. Choose the **Single Tenant** app type. Multi-tenant creation is
   deprecated for new bots (since 31 July 2025), and Huf does not support managed identity bots.
   Create a new Microsoft App ID, or use an existing single-tenant app registration.
2. Record these values. Store the client secret in your secret manager, not in notes:
   - **App ID** (Microsoft App ID, a GUID)
   - **Client secret value** (the secret *value* shown once when created, not the secret ID)
   - **Tenant ID** (the directory the app is registered in)
3. Open **Configuration** on the Azure Bot. Set **Messaging endpoint** to the Gateway webhook URL
   from section 4. It must be HTTPS.
4. Open **Channels**, add **Microsoft Teams**, and accept the terms. The channel must be enabled
   or Teams will not route activities to the bot.

Note: Bot Framework SDK support ended on 31 December 2025. This does not change the REST connector
contract that Huf uses (verify in your tenant against current Microsoft guidance).

## 4. Webhook URL

The messaging endpoint is the generic Gateway webhook for the Gateway, in this exact form:

```
https://<site>/api/method/huf.ai.gateway_webhook.handle_gateway_webhook?gateway_name=<gateway-name>
```

- `<site>` is the public origin of the Huf site, with no trailing slash.
- `<gateway-name>` is the Gateway document name, URL-encoded. It is an identifier, not a credential.
- The URL is built by `getGatewayWebhookUrl` in `frontend/src/utils/gatewayWebhook.ts`. Copy it from the
  Gateway page rather than typing it. Only Slack uses a different route.
- The route is `handle_gateway_webhook` in `huf/ai/gateway_webhook.py`, which reads `gateway_name` from the query string.

## 5. Create the Huf Gateway

1. Go to **Gateways** and create a Gateway. Choose provider **Microsoft Teams**.
2. In the credentials section, enter:
   - **App ID**: the Azure Bot Microsoft App ID.
   - **App password**: the client secret value. The field is write-only. Leave it blank later to keep the stored value.
   - **Tenant ID** (required): the tenant from section 3. Huf rejects a missing tenant ID.
   - **Allowed tenant IDs** (optional): extra tenants whose activities may reach this Gateway. Leave empty to accept only the tenant ID above.
     (planned: the tenant ID and optional allow-list fields are being added to the credential schema.)
3. Paste the webhook URL from section 4 into the Azure Bot messaging endpoint, if you have not done so.
4. Enable the Gateway. A new Gateway starts disabled. The readiness checklist shows what is still missing.

The app password is stored as a secret. Huf never returns it to the browser or writes it to logs.

## 6. Install the app in Teams

1. On the Gateway page, use **Download Teams app package** (planned) to get the generated app package (manifest and icons).
   The manifest `botId` must equal the App ID.
2. Install it in Teams (verify in your tenant):
   - Personal sideload: Apps, Manage your apps, Upload a custom app. Needs the custom app upload policy.
   - Organisation: Teams admin center, Manage apps, Upload new app, then approve it for the org catalog if
     users should find it there.
3. Check that the three IDs are identical: Azure Bot App ID, manifest `botId`, and the Gateway App ID.
   A mismatch causes 401 on every inbound activity.
4. Admin consent is only needed when the app asks for extra Graph scopes or RSC permissions. Plain
   bot messaging needs no Graph consent (verify in your tenant).

## 7. First message (required before replies)

Teams does not let a bot start a conversation with a user who has not messaged it. Huf stores the
conversation reference when it accepts the first verified inbound activity.

- In a personal chat, send any message to the bot first.
- In a group chat or channel, @mention the bot first.
- Replies and the Gateway test message use the stored reference. Until one exists, the test message
  has no recipient to send to.

Proactive messages before the first inbound message are not supported.

## 8. Channels and mentions

- In a channel or group chat, the bot replies only to messages that @mention it.
- If you need the bot to see all messages, the tenant must grant RSC consent, and the app manifest must request it
  (verify in your tenant; the exact permission names are in Microsoft's "enable receive all chat messages" guide).
- Private channels: the bot cannot post in them.
- Replies in channel threads stay in the thread.

## 9. Files

- Inbound (personal chat): Huf receives the file download info from Teams and fetches the file with a short-lived URL.
  The manifest must set `supportsFiles`.
- Outbound (personal chat only): Huf sends a file consent card. After the user accepts, Huf uploads the bytes to the URL Teams gives.
- Group chats and channels: files are shared as Graph or SharePoint links only. Huf does not upload there.
- Files are not available in GCC High, DoD or 21Vianet tenants.

## 10. Limits

| Limit | Value | Source |
|---|---|---|
| Message size | Huf splits outgoing text at about 80 KB on paragraph boundaries. Teams rejects messages above about 100 KB with HTTP 413. | Microsoft message-format guidance; Huf split (planned) |
| Send rate per bot per thread | About 7/s, 8 per 2 s, 60 per 30 s, 1800 per hour | Microsoft rate-limit guidance (values may change) |
| Send rate per app per tenant | About 50 requests/s | Microsoft rate-limit guidance |
| Mention tags | 2 messages per 5 s per thread | Microsoft rate-limit guidance |
| Retries | 429 (honours Retry-After), 412, 502 and 504: up to 3 retries with jitter | Huf client (planned) |

Huf does not send Adaptive Cards yet, so the card-size limit does not apply.

## 11. Security

- **Inbound verification.** Every inbound activity needs an `Authorization: Bearer` JWT. Huf checks:
  RS256 signature from the Bot Framework JWKS, issuer `https://api.botframework.com`, audience equal to the App ID,
  expiry with 5 minutes of clock skew, the `serviceUrl` claim equal to the activity's `serviceUrl`, and the
  `msteams` channel endorsement (missing endorsement returns 403). An unknown key ID triggers one refetch.
  If the JWKS is unavailable and nothing is cached, Huf fails closed (401). (planned: the current
  adapter does not yet validate the full JWT.)
- **Tenant allow-list.** Activities are checked against the tenant ID in `channelData.tenant.id` and the allow-list in section 5.
- **Service URL allow-list.** Only HTTPS hosts are used: `smba.trafficmanager.net`, `*.botframework.com` and `*.trafficmanager.net`.
  Huf rejects IP literals, URLs with user info and redirects. The check runs when a reference is saved and again before every send.
  (planned.)
- **Secrets.** The app password and tokens are masked in logs and API responses. Huf never shows the stored secret, and
  the token cache is keyed by a hash of the App ID, not the secret.
- **Outgoing webhooks are not used.** The older Teams "Outgoing Webhook" route and its HMAC key are being removed (planned).
  Teams should be set up only with the Bot Framework messaging endpoint in section 4.

## 12. Troubleshooting

| Symptom | Likely cause | What to do |
|---|---|---|
| 401 on every inbound activity | App ID does not match the token audience. The manifest `botId` or the Gateway App ID differs from the Azure Bot. | Make the three IDs identical (section 6). |
| 401 with "signature" or "unknown key" | JWKS not reachable, or clock skew over 5 minutes. | Check outbound HTTPS from the server and the server clock. |
| 401 on serviceUrl | The `serviceUrl` claim does not match the activity, or the host is not on the allow-list. | Check that the Azure Bot endpoint is the Teams channel endpoint. Do not add custom proxies. |
| 403 from inbound | Missing `msteams` channel endorsement, or the activity's tenant is not allowed. | Enable the Teams channel on the Azure Bot. Check the tenant ID and allowed tenant IDs. |
| Token request fails (401 from login) | Wrong tenant ID, wrong or expired client secret (ID used instead of value), or app type mismatch. | Confirm the Tenant ID, create a new secret value, and update the App password. |
| Bot does not reply in a channel | Not @mentioned, or RSC not granted. | @mention the bot, or grant RSC consent. |
| Bot does not reply in a 1:1 chat | No stored conversation reference yet. | Send a first message to the bot (section 7). |
| Reply fails with 403 MessageWritesBlocked | The user blocked or uninstalled the bot. | Ask the user to reinstall or unblock it. |
| Reply fails with 404 | Stale service URL or conversation ID. | Send a new message to the bot so a fresh reference is stored. |
| Message rejected with 413 | Message above about 100 KB. | Shorten the reply. Huf splits long text (planned). |
| Reply fails with 429, 412, 502 or 504 | Rate limit or transient Microsoft error. | Retries run automatically. Reduce burst traffic if it persists. |
| No messages arrive after a secret change | Teams caches the registration for several minutes. | Wait, then re-test. |

## 13. Known limitations

- No managed identity (UserAssignedMSI) bots.
- No multi-tenant bots.
- No sovereign clouds (GCC, GCC High, DoD, 21Vianet).
- No proactive messaging before the user's first message. No creating new chats or channels.
- No Adaptive Cards yet.
- Files: personal chat only for outbound upload (section 9).
- Live Azure tenant tests are not part of the automated test suite. Tests use recorded fixtures and fake
  Bot Framework endpoints.
