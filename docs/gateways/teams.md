# Microsoft Teams Gateway Operator Guide

Huf connects to Microsoft Teams through an Azure Bot (Bot Framework channel). Teams delivers
activities to the Huf webhook, and Huf replies through the Bot Framework connector. Behaviour is
taken from code; file references name the source of truth. Never put credentials in this document,
chat or logs.

Scope: single-tenant bots only. Managed identity (UserAssignedMSI), multi-tenant bots and sovereign
clouds (GCC, GCC High, DoD, 21Vianet) are not supported.

Items marked **(verify in your tenant)** rely on Microsoft admin flows or Teams client behaviour that Huf has not tested
against a live tenant (the automated tests use signed fixtures and fake Bot Framework endpoints).

## 1. What the integration does

- Inbound: Teams sends Bot Framework activities to the Gateway webhook. Huf verifies the bearer token
  before any payload is normalized or stored.
- Conversation types: personal (1:1), group chat and team channel.
- Channels and group chats: the bot only sees messages that @mention it, unless the tenant grants
  the resource-specific consent "receive all messages" (RSC). The mention is stripped from the text
  before the agent sees it. Other mentions are kept.
- Threads: channel replies stay in the thread of the inbound message (`;messageid=` in the conversation id).
- Replies: sent from the stored conversation reference, using the service URL Teams sent with that conversation.
- Files: inbound file attachments are recorded as metadata plus the Teams `downloadUrl`; Huf does not download them. Outbound file consent/upload is not implemented (section 9).
- Adaptive Cards: not supported.
- Agent tool: agents can send Teams messages with the `microsoft_teams` tool (section 10).

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
     An activity from any other tenant is acknowledged with HTTP 200 `{"ignored":"tenant"}` and gets no reply.
3. Paste the webhook URL from section 4 into the Azure Bot messaging endpoint, if you have not done so.
4. Enable the Gateway. A new Gateway starts disabled. The readiness checklist shows what is still missing:
   `teams-credentials`, `teams-messaging-endpoint`, `teams-first-message` (done only when a stored, verified Gateway Event with a
   conversation exists; install events alone do not count), `teams-mention-policy` and `teams-allowed-tenants`.
5. Use **Verify connection** (needs Gateway write permission; rate limited to once per 5 seconds per Gateway, a faster click shows
   "Verify connection was run moments ago"). Steps `credentials`, `token` and `token_claims` pass or fail (app id and tenant in the
   token must match the Gateway). `endpoint` and `reference` are informational. Common token errors:
   `AADSTS7000215` invalid secret (use the secret **value**, not the secret ID), `AADSTS7000222` expired secret,
   `AADSTS700016` app not found in the tenant, `AADSTS90002` tenant not found.

The app password is stored as a secret. Huf never returns it to the browser or writes it to logs.

## 6. Install the app in Teams

1. On the Gateway page, use **Download Teams app package** to get the generated app package (manifest and icons).
   The manifest `botId` must equal the App ID. Manifest version 1.29 with the matching `$schema`.
   The site config keys `teams_app_developer_name` (at most 32 characters), `teams_app_website_url`, `teams_app_privacy_url`
   and `teams_app_terms_url` are optional overrides. Defaults: developer name from System Settings app name, website from the
   public https site URL, privacy and terms pointing at the website. If the site URL is not a public https URL the download
   fails and asks you to set `host_name` or `teams_app_website_url`. Override privacy and terms with real policy pages before
   any store submission. The bot manifest sets `supportsFiles` to false (no file upload flow).
   Set overrides with `bench --site <site> set-config <key> <value>`.
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
- Replies and the Gateway test message use the stored reference. The test-send recipient is a
  conversation id that has a stored reference; until one exists there is nothing to send to.
  Adding the bot to a chat or team also stores a reference.

Proactive messages before the first inbound message are not supported.

## 8. Channels and mentions

- In a channel or group chat, the bot sees only messages that @mention it (the Gateway rejects unmentioned ones when mention-required is set). In personal chats it sees every message.
- A gated channel message still stores a verified Gateway Event, so it counts for the `teams-first-message` readiness check even though the agent did not run.
- If you need the bot to see all messages, the tenant must grant RSC consent, and the app manifest must request it
  (verify in your tenant; the exact permission names are in Microsoft's "enable receive all chat messages" guide).
- Private channels: the bot cannot post in them.
- Replies in channel threads stay in the thread.

## 9. Files

- Inbound: for `file.download.info` attachments Huf stores the `downloadUrl` as attachment metadata. It does **not** download the file.
- Outbound file consent and upload: **not implemented**. Group chat and channel files are not handled either.

## 10. Limits, retries and the agent tool

| Limit | Value | Source |
|---|---|---|
| Agent reply size | Replies over 40 KB (UTF-8) are truncated with a "… (truncated)" marker. At most 8 chunks, ~80 KB target per part (paragraph, line, sentence, then hard split); a part over 100 KB is never sent (Teams returns 413). Text format `extendedmarkdown`. | `huf/ai/teams/client.py` |
| Retries | Statuses 429, 412, 502, 504 and network errors: 3 attempts in total (2 retries). `Retry-After` is honoured, capped at 20 s; otherwise exponential backoff with jitter. 45 s wall budget per send, then it fails as transient. A 401/403 from the connector refreshes the bot token once and retries. | `client.py` |
| Send rate per bot per thread | About 7/s, 8 per 2 s, 60 per 30 s, 1800 per hour | Microsoft guidance (verify in your tenant) |
| Send rate per app per tenant | About 50 requests/s | Microsoft guidance (verify in your tenant) |
| Mention tags | 2 messages per 5 s per thread | Microsoft guidance (verify in your tenant) |

Huf does not send Adaptive Cards. `extendedmarkdown` rendering (code fences, tables) and `;messageid=` channel threading are
**(verify in your tenant)**.

If a long reply is split and a later part fails, the error is permanent (no retry) so the user does not see duplicated parts.

### Agent tool `microsoft_teams`

Actions: `send_message`, `list_recent_conversations`, `get_account_info`. It works only inside a run started by this Gateway.
- By default it acts on the **current conversation** only.
- Cross-conversation send/list needs Gateway **write** permission for the actual session user; it is refused for Guest,
  Administrator and the Gateway execution user, so normal agent runs cannot message other conversations.
- Per run: 5 sends and 3 failed sends at most. Text up to 8000 characters. Conversation display names are not returned.
- The recipient must have a stored conversation reference.

## 11. Security

- **Inbound verification.** Every inbound activity needs an `Authorization: Bearer` JWT. Huf checks RS256 signature from the
  Bot Framework JWKS, issuer `https://api.botframework.com`, audience equal to the App ID, expiry with 5 minutes of skew,
  the `serviceUrl` claim equal to the activity's `serviceUrl`, and that the signing key endorses the channel. The activity
  `channelId` must be `msteams`. Unknown key IDs trigger a limited refetch. If JWKS is unavailable and nothing is cached, Huf
  fails closed. Any verification failure returns **HTTP 401** with no side effects (the Microsoft spec suggests 403 for a missing
  endorsement; Huf does not implement that). Non-Teams channels (Web Chat, Direct Line) are rejected.
- **Replay caveat.** The token is not bound to the request body (protocol-inherent). A captured token can be replayed with a different
  body until it expires (about an hour).
- **Tenant allow-list.** `channelData.tenant.id` must equal the Tenant ID or an allowed tenant ID. Otherwise HTTP 200 `{"ignored":"tenant"}`, no reply.
- **Service URL allow-list.** Only `https://smba.trafficmanager.net/<region>/` is accepted (no IP literals, user info, ports,
  redirects). Checked when a reference is saved and before every send. GCC (`smba.infra.gcc.teams.microsoft.com`) and GCC High / DoD
  (`smba.infra.gov.teams.microsoft.us`, `smba.infra.dod.teams.microsoft.us`) hosts are **not supported** yet.
- **Secrets.** The app password is write-only and never logged. The token cache key includes a hash of the secret.
- **Conversation references** are scoped per Gateway.
- **Legacy Outgoing Webhook.** A route for the old Teams Outgoing Webhook still exists in this build
  (`huf/ai/tools/teams_webhook.py`) but is unsupported and being removed. Use only the Bot Framework endpoint from section 4.

## 12. Troubleshooting

| Symptom | Likely cause | What to do |
|---|---|---|
| 401 on every inbound activity | App ID does not match the token audience. The manifest `botId` or the Gateway App ID differs from the Azure Bot. | Make the three IDs identical (section 6). |
| 401 with "signature" or "unknown key" | JWKS not reachable, or clock skew over 5 minutes. | Check outbound HTTPS from the server and the server clock. |
| 401 on serviceUrl or channel | The `serviceUrl` claim does not match the activity, or the activity came from Web Chat / Direct Line instead of Teams. | Test from Teams, not Web Chat. Do not add custom proxies. |
| 200 but no reply | Tenant not allowed (`ignored: tenant`), service URL not on the allow-list (`ignored: service_url`), or unmentioned channel message. | Check Tenant ID / allowed tenant IDs; @mention the bot. |
| Token request fails (AADSTS code in the error) | Wrong tenant ID, wrong or expired client secret (ID used instead of value), or app type mismatch. | Confirm the Tenant ID, create a new secret value, and update the App password. |
| Bot does not reply in a channel | Not @mentioned, or RSC not granted. | @mention the bot, or grant RSC consent. |
| Bot does not reply in a 1:1 chat | No stored conversation reference yet. | Send a first message to the bot (section 7). |
| Reply fails with 403 MessageWritesBlocked | The user blocked or uninstalled the bot. | Ask the user to reinstall or unblock it. |
| Reply fails with 404 | Stale service URL or conversation ID. | Send a new message to the bot so a fresh reference is stored. |
| Message rejected with 413 | Message above about 100 KB. | Huf truncates and splits long replies; a single part over 100 KB fails. |
| Reply fails with 429, 412, 502 or 504 | Rate limit or transient Microsoft error. | Retries run automatically. Reduce burst traffic if it persists. |
| No messages arrive after a secret change | Teams caches the registration for several minutes. | Wait, then re-test. |

## 13. Known limitations

- No managed identity (UserAssignedMSI) bots; no multi-tenant bots.
- No sovereign clouds (GCC, GCC High, DoD, 21Vianet); their service URLs are rejected.
- No file upload or consent flow; inbound files are not downloaded.
- No typing indicator. No Adaptive Cards.
- No proactive messaging before the user's first message; no creating new chats or channels.
- Gated (unmentioned) channel messages still count as the "first message" for readiness.
- Live Azure tenant tests are not part of the automated suite.
