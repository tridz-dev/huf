# Microsoft Teams gateway: administrator setup (slice 1)

Scope: direct mode only. Huf receives Bot Framework activities itself, using a single-tenant
Entra app and an Azure Bot resource, in the Microsoft commercial (global) cloud. There is no
separate adapter service, no Graph access and no OAuth redirect. See UNSUPPORTED.md.

Every statement below about Microsoft portals, menu names, field names, licensing or policies
reflects what the Huf code and its in-product text assume. Treat each one as **verify against
current Microsoft documentation** before relying on it. Microsoft changes these portals often.

Official documentation (from SPEC section 25):

- Teams SDK overview (D1): https://learn.microsoft.com/en-us/microsoftteams/platform/teams-sdk/welcome
- App manifest schema (D3): https://learn.microsoft.com/en-us/microsoftteams/platform/resources/schema/manifest-schema
- Proactive messages (D4): https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/conversations/send-proactive-messages
- Upload a Teams app (D10): https://learn.microsoft.com/en-us/microsoftteams/platform/concepts/deploy-and-publish/apps-upload
- Bot Connector authentication (D11): https://learn.microsoft.com/en-us/azure/bot-service/rest-api/bot-framework-rest-connector-authentication?view=azure-bot-service-4.0
- Card types and surface support (D7): https://learn.microsoft.com/en-us/microsoftteams/platform/task-modules-and-cards/cards/cards-reference

## 1. Prerequisites

1. A Microsoft 365 work or school tenant with Teams, and a person who can register apps in
   Microsoft Entra and create Azure resources (an Azure subscription is needed for the Azure Bot
   resource) and upload apps in Teams. Whether sideloading is allowed is a tenant policy
   (verify against current Microsoft documentation, D10).
2. A Huf site reachable from the internet over **HTTPS** with a certificate Microsoft accepts.
   The diagnostics check `messaging_endpoint` warns when the URL is not https.
3. Huf background workers and the scheduler running. Replies go through a durable outbox that is
   drained by the `short` queue workers (message handling uses the `default` queue) and a once-a-minute scheduler job (ROUTES_AND_CONFIG.md).
4. The Python package `PyJWT>=2.8.0` installed (declared in `pyproject.toml`).
5. Outbound HTTPS from the Huf server to `login.botframework.com`, `login.microsoftonline.com`
   and the Bot Connector host Teams sends in each activity (`smba.trafficmanager.net`).
6. A Huf user with the System Manager role (or write permission on the Gateway) to do the setup.
7. An agent (or flow) to answer, and a Gateway "Run as user" (`execution_user`). Huf requires
   this field to be set even though Teams people run as their own linked Huf user.

## 2. Microsoft side (verify each step against current Microsoft documentation)

1. **Entra app registration.** Create an app registration that is **single-tenant**
   ("accounts in this organizational directory only"). Record the Application (client) ID and
   the Directory (tenant) ID. Create a client secret and copy its **Value** (not the Secret ID).
   Huf cannot see the expiry date of the secret; track it yourself.
2. **Azure Bot resource.** Create an Azure Bot that uses that existing app registration, type
   single-tenant. Add the **Microsoft Teams** channel.
3. **Messaging endpoint.** Set it to the exact URL Huf generates (section 4 below).
4. Do not add API permissions or admin consent for Graph. Slice 1 does not call Graph.

## 3. Huf side

1. Open Integrations, add a Gateway with channel **Microsoft Teams**, and connect its
   Integration Settings. Enter the three credentials (keys must be exactly these):

   | Key | Label in Huf | Secret | Source |
   |---|---|---|---|
   | `app_id` | Microsoft App ID | yes | Entra Application (client) ID |
   | `app_password` | Microsoft App Secret / Password | yes | client secret Value |
   | `tenant_id` | Directory (tenant) ID | no | Entra Directory (tenant) ID |

   The adapter refuses to start if any is missing. Credentials are never shown again after saving.
2. Set the Gateway "Run as user", a default route (default agent or flow) or a Gateway Binding.
3. Admission policies. The generic Gateway policies still apply to Teams: `direct_policy`
   (default `Allow list`), `room_policy` (default `Allow list`), `room_sender_policy` (default
   `Allow list`) and `mention_required` (default on). The sender id Huf checks is the person's Entra
   object id. With the defaults a person who is not on an allow list gets a Rejected event
   ("Sender is not approved for this gateway") for ordinary messages. The four commands
   (`help`, `connect`, `status`, `disconnect`) are answered before admission, so they work
   regardless. For a pilot, set `direct_policy` to `Open` or create Gateway Access Entries.
   **This interaction is not described in the spec or plan; confirm it on the bench.**
4. Enable the Gateway (`is_enabled`). A disabled gateway returns HTTP 403 to Microsoft.

Fields `unmapped_policy` ("When a person is not linked") and `private_reply_policy` exist on the
Gateway form but are Slack settings. The Teams code ignores both. Teams people who are not
linked are always asked to connect; they are never run as the service user. Where answers go
in channels is governed by Teams Gateway Settings `private_output_policy` (ROUTES_AND_CONFIG.md).

## 4. Setup wizard (Gateway > Teams setup panel) mapped to the steps

The panel title is "Teams setup". It contains seven numbered sections:

| Wizard section | What it does | Backend call |
|---|---|---|
| 1. Create the Entra app and Azure Bot | Shows and copies the messaging endpoint; links to Entra and Azure | `teams_diagnose` (endpoint) |
| 2. Enter your app details | Text only: use the Credentials tab (section 3.1) | none |
| 3. Test the connection | Runs the diagnostics checks (credentials, token) | `teams_diagnose` |
| 4. Allowed organisations | Edits the tenant allowlist | `get_teams_settings`, `save_teams_settings` |
| 5. Download the Teams app package | Downloads the zip for a chosen version | `download_teams_app_package` |
| 6. Upload it in Teams | Text and links to Teams admin center / Teams | none |
| 7. Say hello to the bot | Shows the `last_inbound` check; can poll for the first message | `teams_diagnose` |

Two further panels: "Teams people" (list, link and revoke people) and "Teams diagnostics"
(all checks and a redacted support bundle). The wizard has no per-step Save draft/Back; the spec's
section 7 draft/back behaviour is not implemented (see UNSUPPORTED.md).

**Messaging endpoint, exact form** (from `teams_diagnostics.endpoint_url`):

```
<site URL>/api/method/huf.ai.gateway_webhook.handle_gateway_webhook?gateway_name=<Gateway document name, URL-encoded>
```

`<site URL>` is `frappe.utils.get_url()` (the site's configured `host_name`, or the request host).
Confirm the panel shows the public https host, not a localhost or internal name. The URL contains
the Gateway name only, no secret. The route also accepts GET (answered only for adapters that
define `verify_url`; the Teams adapter does not), so use Teams or the Azure "Test in Web Chat"
(verify against current Microsoft documentation) rather than a browser to test it.

## 5. Allowed organisations

Teams Gateway Settings `allowed_tenants`: one Entra tenant GUID per line (commas and semicolons also
accepted). Leave empty to allow **only the home tenant** (the `tenant_id` credential). A non-GUID
entry is rejected on save. Events whose tenant is missing, unparseable or not allowed are dropped
with reason `tenant_not_allowed`. Because slice 1 supports a single-tenant bot only, entries other
than the home tenant are not expected to work; see UNSUPPORTED.md (multi-tenant).

## 6. App package: download and upload

1. In section 5 of the wizard, enter a semantic version (`1.0.0`), click Download package.
   Raise the version on every new download (Teams rejects a same-version re-upload; verify).
2. The zip contains `manifest.json`, `color.png` (192x192) and `outline.png` (32x32). The manifest
   uses schema 1.19 (pinned in code; **verify against D3 before release**). The manifest `id` and
   `bots[0].botId` are both the `app_id` credential. Scopes: personal, team, groupChat. Bot commands
   listed: help, connect, status, disconnect. Permissions: `identity`, `messageTeamMembers`.
   `validDomains` holds the Huf site host. No SSO, RSC or webApplicationInfo block is generated.
3. The developer name is "Huf"; website is the site URL; privacy and terms URLs are
   `<site>/privacy` and `<site>/terms`. **Huf does not currently serve those two pages** (not found in
   this repository). Teams store validation or tenant review may require working URLs; provide
   your own pages or edit the manifest before upload (verify, D3, D10).
4. Upload: organisation-wide in the Teams admin center, Manage apps, Upload new app; or
   per-user in Teams, Apps, Manage your apps, Upload an app (verify, D10). An app registration does
   not install the app; people (or an admin policy) must install it.
5. After upload record the version in Teams Gateway Settings `app_package_version` (shown by the
   `app_package` diagnostic). The wizard does not save it for you; it is a field on the settings
   record (via `save_teams_settings` or the Desk form).

## 7. Pilot users and first-message verification

1. Install the app for a small test group first (admin policy or personal upload).
2. Each pilot user opens a personal chat with the bot and sends `help`. Expected: a reply with the
   first-contact text and "Send connect to link your account." Note: the four commands are answered
   by a filter before a Gateway Event row is created, so `help` does **not** make the wizard's
   `last_inbound` line turn green (it reads Gateway Event rows). The wizard text that says to send
   "help" for that purpose does not match the code. To see `last_inbound`, send an ordinary
   non-command message (for example "hello"); it creates a Gateway Event even if admission later rejects it.
3. The user sends `connect`, opens the link while logged in to Huf, and confirms (USER_HELP.md).
   Alternatively an admin links a person in "Teams people" by tenant GUID, Entra object id and Huf user.
4. In the diagnostics panel `conversation_references` shows an installed personal conversation once Teams
   has sent an install event or the user has sent an ordinary message (commands alone do not create the
   reference); `linked_users` shows the count.
5. Ask the user a real question. The reply is queued in the outbox and delivered by a worker; on
   failure see Troubleshooting in ROUTES_AND_CONFIG.md and the `outbox` check.

Run REAL_TENANT_CHECKLIST.md before declaring the tenant ready.
