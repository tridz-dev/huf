# WhatsApp Gateway: Operator Runbook

This runbook describes how the WhatsApp gateway behaves in the current code: how to set it up, how it routes messages, and how to troubleshoot it. It covers only what the code does.

Source of truth:

- `huf/ai/gateway_adapters/whatsapp.py`: adapter (ingress verification, parsing, outbound sends)
- `huf/ai/gateway_adapters/whatsapp_bridge.py`: the only module that touches `frappe_whatsapp` DocTypes
- `huf/ai/whatsapp/management.py`: whitelisted management API
- `huf/ai/gateway_webhook.py`: `handle_gateway_webhook` (the single Meta callback)
- `huf/ai/tools/whatsapp.py`: agent tool

---

## 1. Overview

Huf's WhatsApp gateway works without `frappe_whatsapp`. It has two modes.

**Direct mode** (Huf core only)

- Huf receives Meta webhooks, verifies them, and runs the agent.
- Replies are posted to the Meta Graph API (`v25.0`) using the credentials in the connected Integration Settings.
- No `frappe_whatsapp` DocTypes are required.

**Bridge mode** (`frappe_whatsapp` installed and the Gateway's `whatsapp_account` field set)

- Replies are created as `WhatsApp Message` (Outgoing) rows, which send the message through `frappe_whatsapp`.
- The inbound message is mirrored into `WhatsApp Message` for history.
- Template management and message listing from Huf use `frappe_whatsapp` DocTypes.

Huf never imports `frappe_whatsapp` at module load. The bridge checks for the DocTypes `WhatsApp Message`, `WhatsApp Templates` and `WhatsApp Account`. If any is missing, the bridge reports itself unavailable.

> **Template management and message history require the optional connector app (`frappe_whatsapp`, "bridge mode").** Without it, Huf still receives messages, runs the agent and replies (including the template fallback), but the template list/create/delete/sync, message and conversation listing, and the WhatsApp Message history are unavailable (`bridge_unavailable`).

### Known limits

- **One enabled Gateway per phone number.** A signed payload for a `phone_number_id` that does not match the gateway is ignored (HTTP 200) and the gateway's `last_error` says so. Several numbers need several Gateways; see [Multiple WhatsApp gateways](#multiple-whatsapp-gateways).
- **Non-text inbound** (location, contacts, reactions) is acknowledged but does not start a run and does not open the 24h window in Huf. Known limitation.
- **72-hour click-to-WhatsApp windows are not modelled.** Huf always applies the conservative 24h rule.
- The window is anchored on the customer's own message timestamp, so Meta redelivering an old webhook (up to about 7 days) does not reopen it.

### What each mode supports

| Capability | Direct mode | Bridge mode |
|---|---|---|
| Receive signed text, interactive and button messages and run the agent | Yes | Yes |
| Duplicate Meta deliveries (same message id) produce one run | Yes | Yes |
| Free-form reply inside the 24h window | Yes, via Graph API | Yes, via `WhatsApp Message` Outgoing |
| Template fallback when the window is closed (Gateway `fallback_template` set) | Yes, via Graph API | Yes, via `WhatsApp Message` |
| Clear failure when the window is closed and no fallback is set | Yes | Yes |
| Inbound messages mirrored into `WhatsApp Message` | Only if `frappe_whatsapp` is installed and a WhatsApp Account resolves | Yes |
| Outbound messages recorded in `WhatsApp Message` | No | Yes |
| Delivery status callbacks forwarded to `frappe_whatsapp` | No | Yes (only for known message ids) |
| Template list, create, delete and status sync | No (`bridge_unavailable`) | Yes |
| Message and conversation listing in the management API | No (`bridge_unavailable`) | Yes |
| Outbound media (image, document, audio, video) inside the 24h window | Yes, by link or Meta media id | Yes, by link only |
| Rich templates: header, footer, buttons | No (`bridge_unavailable`) | Yes (see section 4.4) |
| Template send with header and button parameters | Yes, via Graph API | Yes (see section 4.4) |
| Inbound media download | Yes, best-effort in the background job (see section 7) | Yes, best-effort in the background job (see section 7) |

Note: the management API and the agent tool's `list_templates` and `create_template` actions need `frappe_whatsapp`. The agent tool's `send_message`, `send_media` and `send_template` do not. Without `frappe_whatsapp`, they call the Graph API directly.

---

## 2. Prerequisites

### Meta side

1. A Meta app with the WhatsApp product added.
2. A WhatsApp Business phone number, and its **Phone Number ID**.
3. A **permanent system-user access token** with permission to send messages and manage templates for the WhatsApp Business Account. Do not use the temporary 24-hour token from the API setup page.
4. The Meta app's **App Secret** (App settings > Basic). The gateway uses it to verify webhook signatures.
5. A **webhook verify token**: any string you choose. It must match the value you enter in Huf.
6. The **WhatsApp Business Account ID** if you plan to use template management. The sync reads templates by this ID.

### Optional: `frappe_whatsapp` (bridge mode)

Install the app on the bench and site:

```bash
bench get-app https://github.com/shridarpatil/frappe_whatsapp
bench --site <site> install-app frappe_whatsapp
```

You don't create the **WhatsApp Account** yourself. Saving the WhatsApp credential (3.1) creates it, or updates the one with the same `phone_id`, and links it to every gateway that uses the credential. A gateway connected to an existing credential later is linked on save too. The account is a copy of the credential: edit the credential, not the account. The code reads these fields:

| Field | Used for |
|---|---|
| `phone_id` | Phone Number ID. Checked against inbound `metadata.phone_number_id` |
| `token` | Access token (stored as a Password field) |
| `business_id` | Template list and sync |
| `url` | Graph base URL (defaults to `https://graph.facebook.com`) |
| `version` | Graph API version (defaults to `v25.0`) |
| `app_id` | Meta app links in the console |
| `is_default_outgoing` | **Ignored by Huf's gateway, webhook and management code.** Only the non-gateway agent tool uses it (when it is called without `gateway_name`) |
| `status` | Used only by that same non-gateway tool fallback (first account with status `Active`) |

The generated account is never marked as frappe_whatsapp's default incoming or outgoing account and never gets a webhook verify token, so frappe_whatsapp's own webhook can't pass Meta's verification in place of Huf's.

Huf never guesses an account for a gateway. Every gateway-side action (inbound mirroring, replies, template sync and updates, message and template listings) resolves the account through the Gateway's `whatsapp_account`; with none linked, the gateway runs in direct mode and mirroring is skipped (logged). frappe_whatsapp's own *default outgoing* and *Active* flags are therefore irrelevant to Huf, whatever they are set to.

---

## Overview and Settings

Open Manage WhatsApp and pick a gateway at the top right. The page has four tabs, and the tab and gateway are kept in the URL (`?tab=`, `?gateway=`) so links and reloads land in the same place.

- **Overview** (default): a health banner (working, needs attention, blocked, not set up, turned off) with a "Check now" button that refreshes the status and checks the access token with Meta, the setup checklist, the callback URL and verify token details, and the last 24 hours of activity.
- **Messages** and **Templates**: the message log and template management. They need the optional WhatsApp Business connector app; without it these two tabs say so and everything else keeps working.
- **Access**: people waiting for approval, approved people and revoked people.
- **Settings**: credentials status and the token check, reply rules (fallback template and who can message), the linked WhatsApp account, and an "Edit in gateway settings" link to the channel's page in Huf (Gateways > the channel > Channel tab).

Checklist steps that point at credentials, the app secret or the on/off switch jump to the matching section under Settings in the Channels app. "Approve your first sender" jumps to Settings > Access.

Every WhatsApp gateway setting can be edited on the channel's **Channel** tab: who can message (pairing reply, limits and the people list), opt-out keywords and limits, replies (typing, voice notes, link previews, error text, retries, fallback template), what the agent may send, calls and solutions routing. **Connect agent** on the channel page picks the agent that answers the channel, creating the gateway when there is none.

---

## 3. Setup steps

### 3.1 Integration Settings (credentials)

Add a WhatsApp channel under Gateways > Channel credentials (an **Integration Settings** record for service `whatsapp`) with these credentials:

| Key | Required | Notes |
|---|---|---|
| `phone_number_id` | Yes | Not secret. Meta Phone Number ID |
| `business_account_id` | Yes | Not secret. WhatsApp Business Account (WABA) ID |
| `app_id` | Yes | Not secret. Meta App ID |
| `access_token` | Yes | Permanent system-user token. Stored as Password |
| `app_secret` | Yes | Meta App Secret. Without it, every POST delivery is rejected |
| `webhook_verify_token` | Yes | Any phrase. Must match the verify token entered in Meta |
| `graph_api_version` | No | Defaults to `v25.0` |

On save Huf checks the values with Meta: the token is valid, the phone number exists and the token can use it, the token can manage the business account, and the phone number belongs to it. A wrong value refuses the save with the reason; Meta being unreachable only warns. Then it creates or updates the WhatsApp Account (when `frappe_whatsapp` is installed), copies the phone number ID and business account ID onto the gateways using the credential, subscribes the app to the business account's webhooks (`POST /{waba}/subscribed_apps`) and syncs templates in the background.

The adapter itself only needs `phone_number_id`, `access_token`, `webhook_verify_token` and `app_secret`, so credentials saved before the other keys existed keep receiving and sending; the missing keys are asked for the next time the credential is saved.

Agent privilege flags are Check fields on the Gateway itself (not credential rows); see section 6.

### 3.2 Gateway

Create a **Gateway**:

| Field | Value |
|---|---|
| Channel (`provider`) | `WhatsApp` |
| Connected integration (`integration_settings`) | The Integration Settings record from 3.1 |
| Phone number ID (`phone_number_id`) | Read-only and indexed. Derived on save from the `phone_number_id` credential of the connected integration. See [Multiple WhatsApp gateways](#multiple-whatsapp-gateways) |
| WhatsApp Account (`whatsapp_account`) | Set automatically from the credential when `frappe_whatsapp` is installed (bridge mode). Its `phone_id` must equal this gateway's phone number ID |
| Fallback template (`fallback_template`) | Optional. Name of an approved template with no variables. Used when a reply is due and the 24h window is closed |
| Fallback template language (`fallback_template_language`) | Language code of that template. Defaults to `en_US` |
| Run as user (`execution_user`) | Least-privileged Huf user. Never `Administrator` |
| Direct-message policy (`direct_policy`) | `Allow list` (default), `Pairing`, `Open` or `Disabled` |
| Enabled (`is_enabled`) | Checked |

Admission:

- With `Allow list`, a direct message is denied unless an approved **Gateway Access Entry** matches the sender. The sender's `external_id` is stored digits-only (see section 8).
- With `Pairing`, an unknown sender creates a pending pairing request and gets a reply with their pairing code (`pairing_reply_enabled`, on by default, capped by `pairing_reply_daily_limit`). The triggering message is not executed. If replies were off when the request was created, the code is sent with the sender's next message once they are turned on. Approving the request sends the sender a welcome message.

Managing people (the People list on the channel's Channel tab, or Settings > Access in the Channels app):

| Action | Effect |
|---|---|
| Decline (waiting) / Remove access (approved) | Entry becomes `Revoked`. The agent stops replying at once. After 24 hours (`ACCESS_REREQUEST_COOLDOWN_HOURS`) their next message starts a new pairing request. |
| Restore access (removed) | Approved again directly, with the welcome message. |
| Block | Entry becomes `Blocked`: ignored silently and never paired again. Never overrides an opt-out (it lands on `Blocked` if they later send START). |
| Unblock | Back to removed with no cooldown, so they can ask again straight away. |
| Add number | Approves a number by hand without messaging it. This is how people get in under the `Allow list` policy. |
| Opted out | Read-only. Only the person can undo it, by sending START. |

### 3.3 Register the callback in Meta

In the Meta app, under WhatsApp > Configuration > Webhooks:

1. **Callback URL**: Huf's endpoint for this gateway:

   ```
   https://<site>/api/method/huf.ai.gateway_webhook.handle_gateway_webhook?gateway_name=<Gateway name>
   ```

   Replace `<Gateway name>` with the Gateway document name, URL-encoded if needed.

2. **Verify token**: the same value as `webhook_verify_token`.
3. Click **Verify and save**. Meta sends a GET request. Huf returns `hub.challenge` when the token matches.
4. Subscribe to these fields:
   - `messages`
   - `message_template_status_update`
   - `message_template_quality_update` (optional)
   - `template_category_update` (optional)

   Huf forwards these best-effort. A rejected/paused/disabled template, a quality drop to LOW or RED, or a category change is written to the `last_error` of every gateway linked to that template's WhatsApp Account (found by the WABA id in the payload) whose fallback template matches. `played` delivery statuses are accepted and ignored. The verification GET requires `hub.mode=subscribe` when `hub.mode` is sent.

**Security: the callback must be Huf's endpoint, never `frappe_whatsapp`'s webhook.** Meta allows one callback URL per app. `frappe_whatsapp` ships an unsigned webhook route. If that route is configured as the callback, Huf's signature verification is bypassed. Huf cannot detect this from its side. Check the callback URL in Meta. The management API's setup status returns the correct URL and a warning string to compare against.

**The connector's own webhook stays live.** Installing `frappe_whatsapp` leaves `/api/method/frappe_whatsapp.utils.webhook.webhook` reachable by anyone, with no signature check. Anyone who can reach it can write fake rows into `WhatsApp Message` and pollute the message history. Huf does not read those rows to decide the 24h window, but the history views would show them. Disable it by blocking the route at the reverse proxy, for example in nginx:

```nginx
location = /api/method/frappe_whatsapp.utils.webhook.webhook {
    return 403;
}
```

Place it in the site's `server` block before the generic Frappe proxy location. Meta then only reaches Huf's signed endpoint.

### 3.4 Verify the setup

Call `huf.ai.whatsapp.management.get_setup_status` (System Manager or Huf Admin), or open Home in the Channels app (`/channels/whatsapp`, which opens the number's Home at `/channels/whatsapp/n/<gateway>/home`; the old `/whatsapp` URL redirects there). It reports:

- `bridge_available`
- the WhatsApp Accounts found
- for each WhatsApp gateway: its webhook URL, whether `app_secret` and `webhook_verify_token` are present, and a `failing_checks` list. `account_phone_mismatch` is listed when the linked WhatsApp Account's `phone_id` differs from the credential `phone_number_id`

A healthy gateway has an empty `failing_checks` list. Send a test message from Meta or from a WhatsApp phone to the business number. Confirm a Gateway Event and an agent run appear.

The **Test message** box on the Channel tab sends to a phone number with country code. Inside the 24-hour window it sends plain text; outside it (always, on a fresh setup) it sends the gateway's fallback template, or Meta's `hello_world` sample template when none is set.

### 3.5 Troubleshooting

| What you see | Meaning | Fix |
|---|---|---|
| Health reason `signature_failed` ("Meta is calling us, but the signature check failed. Check the app secret."), next step `fix_app_secret` | Meta reached the callback URL, but the `X-Hub-Signature-256` check failed (or the GET verify token did not match). Almost always a wrong or stale App Secret. | Copy the App Secret again from the Meta app (App settings, Basic) into the Integration Settings credential `app_secret`. The error clears when the next valid event arrives, or after 24 hours. |
| Health reason `senders_waiting`, checklist step "Approve your first sender" | Messages arrive but come from people nobody has approved yet (Pairing). The agent does not run for them. | Approve them under Settings > Access or the channel's Channel tab. |
| Health reason `no_events_yet` ("Meta hasn't sent us anything yet") | Meta has not called the callback URL, or the `messages` field is not subscribed. | Check the callback URL and the subscription in Meta. If Meta's "Verify and save" succeeded, the checklist step "webhook" is already done. |

How the signature signal works: when a WhatsApp webhook call fails the signature (POST) or the verify-token check (GET), Huf stores one timestamp on the Gateway (`last_signature_failure_at`) and nothing else: no headers, body, token or secret. A successful GET verification stores `last_verify_ok_at`. Each is written at most once a minute per gateway, so unauthenticated traffic cannot cause a write storm. The failure counts only for 24 hours and only while no valid event has arrived after it. Trade-off: because the callback is unauthenticated, anyone who knows the URL can make the gateway show "blocked" by sending a bad signature; it clears with the next valid message and never affects message handling.

---

## Multiple WhatsApp gateways

Run one Huf **Gateway per WhatsApp phone number**. Each Gateway has its own Integration Settings (phone number ID, access token, verify token, app secret), its own callback URL, and optionally its own `frappe_whatsapp` WhatsApp Account. Inbound events, the 24-hour window, conversations (`channel_id` `gateway:<name>`), replies and message history are all kept per Gateway, even when the same customer writes to several of your numbers.

### Rules

- **Uniqueness.** Two *enabled* WhatsApp Gateways cannot share a `phone_number_id`. Saving the second one fails with a message naming the first. A *disabled* Gateway may keep a duplicate; enabling it is what is checked, so you can swap a number from one Gateway to another by disabling the old one first.
- **Account linking.** `whatsapp_account` is optional. When `frappe_whatsapp` is installed and an account is linked, an enabled Gateway only saves if that account exists and its `phone_id` equals the Gateway's `phone_number_id`. Link each Gateway to the account of its own number. Without `frappe_whatsapp`, the link is ignored and the Gateway runs in direct mode.
- **No default account.** Huf's gateway, webhook and management paths never fall back to `is_default_outgoing` or the first `Active` account (see section 2). A Gateway with no linked account sends directly through Graph and its inbound messages are not mirrored into `WhatsApp Message`.
- **Everything is scoped by Gateway.** The management API takes `gateway_name` and derives the account from it. Listing messages, conversations, templates or drafts without a Gateway (or an account you may access) returns `gateway_required`. Sending needs write authority on the Gateway.
- **Secrets are per Meta app.** The app secret that signs webhooks belongs to the Meta *app*, not the number. Two Gateways on the same Meta app need the same `app_secret` repeated in each one's Integration Settings; Gateways on different apps use different secrets.

### Topologies

**A. Separate Meta apps (simplest).** One Meta app per number. Each app's callback URL is that Gateway's own URL (section 3.3), each with its own verify token and app secret. Nothing else to configure.

**B. Several numbers under one Meta app.** Meta allows only one callback URL per app by default, so route each number elsewhere with Meta's callback override (see [Meta's documentation](https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/override/); verify the request shapes there before using them):

- *Per phone number*: `POST /<BUSINESS_PHONE_NUMBER_ID>` with a `webhook_configuration` object containing `override_callback_uri` and `verify_token`.
- *Per WhatsApp Business Account*: `POST /<WABA_ID>/subscribed_apps` with `override_callback_uri` and `verify_token`.

Set `override_callback_uri` to the Huf URL of the Gateway that owns that number (`.../handle_gateway_webhook?gateway_name=<Gateway name>`) and `verify_token` to that Gateway's `webhook_verify_token`. Because the numbers share an app, all of those Gateways use the same `app_secret`.

**Template and account webhooks are not overridable.** `message_template_status_update`, `message_template_quality_update`, `template_category_update` and account-level events always go to the app's *default* callback URL, whichever number or WABA they concern. Make the default callback the URL of one of your Gateways (it only needs a valid signature for the app). Huf does not treat the receiving Gateway as the template's owner: it routes the update by the WABA id in the payload (`entry[].id`, matched against `WhatsApp Account.business_id`) to the right account. An update for a WABA that no WhatsApp Account carries is ignored with a log warning. Without `frappe_whatsapp` there are no accounts, so template state is recorded unscoped and only the receiving Gateway can be flagged for a bad fallback template.

### Template names

`frappe_whatsapp` names a template document `<name>-<language>` and keeps `template_name` unique for the whole site, so one name and language cannot exist on two accounts at once. Creating or importing such a template for a second account fails with `template_name_taken_by_other_account` (sync lists it under `skipped_reasons`); the first account's template is never overwritten. Pick a different template name for the second account. Huf's own review and quality state (`WhatsApp Template State`) is keyed `<account>::<template>`, and drafts carry their account, so state never mixes between accounts.

## Message log

`huf.ai.whatsapp.management.list_message_log` (GET) returns a gateway-scoped, newest-first log of the messages
a WhatsApp gateway handled. It needs the same access as `list_messages` (read on the Gateway; the account is
derived from `Gateway.whatsapp_account`).

- Parameters: `gateway_name`, `direction` (`in`/`out`), `status`, `agent`, `template`, `phone`, `q`,
  `date_from`, `date_to`, `cursor`, `limit` (1-100, default 50). Returns `{success, items, next_cursor, has_more}`.
- Paging is keyset-based on `(creation desc, name desc)`; pass `next_cursor` back unchanged (opaque).
- With frappe_whatsapp installed the rows come from `WhatsApp Message` for the gateway's account and are
  joined to Gateway Events: inbound rows by `provider_event_id`, agent replies by `reply_message_id`. Each item has
  `sent_by` = `customer`, `agent`, `template` (template send with no event) or `manual`.
- Without frappe_whatsapp (direct mode) the log is built from Gateway Events only: one inbound row per event
  plus one outbound row per sent reply. Reply bodies are not stored, so those rows have an empty `text`.
- `list_message_log_filters(gateway_name)` returns the values for the filter dropdowns.
- Delivery tracking: after a reply is sent the Gateway Event stores `reply_message_id` and `reply_status`
  (`sent`). Meta status webhooks (`sent`, `delivered`, `read`, `failed`) update `reply_status` on the event of the
  receiving gateway; a failure also stores a redacted `delivery_error` (code and title).
- Migrate adds two Huf-owned indexes on `WhatsApp Message` (`whatsapp_account, creation` and `message_id`).
  It is idempotent and skipped when frappe_whatsapp is absent.

## App tile

Huf seeds a first-party `WhatsApp` tile in the app launcher (it opens the Channels app at `/huf/channels/whatsapp`, category Communicate) on install
and migrate. An admin's `enabled` choice is never overwritten. The tile is shown only to System Manager, Huf Admin
or users with `system.integrations.manage`, and only while at least one enabled WhatsApp gateway exists
(`huf.ai.whatsapp.management.can_launch_whatsapp_app`).

## 4. The 24-hour window and templates

### 4.1 Window rule

The customer-service window is computed only from signed inbound Gateway Events for the same gateway and sender (`verified_sender = 1`). It is **open** for 24 hours after the sender's latest signed inbound message. `WhatsApp Message` rows are never used to decide the window.

Inside the window, replies are sent as free-form text.

### 4.2 Outside the window

When a reply is due and the window is closed:

1. If the Gateway has a `fallback_template`, the reply is sent as that template with no variables (language from the Gateway's `fallback_template_language`, default `en_US`; in bridge mode the language of the matching WhatsApp Templates row is used when found). The Gateway Event stays `Succeeded` and its `error_message` reads "Fallback template sent; agent reply suppressed (24h window closed)".
2. If there is no fallback template, the send raises `WhatsAppWindowClosed`. The Gateway Event is set to status `Failed`, and its `error_message` (up to 500 characters) reads like `WhatsApp delivery failed: ...`. A log entry is also written. Nothing is retried in a loop.

Approval and pairing notifications follow the same rule. If the window is closed and no fallback is set, they are skipped and logged. The approval itself is not rolled back.

### 4.3 Template management

**UI**: Templates in the Channels app (`/channels/whatsapp/n/<gateway>/templates`).

**Management API** (`huf.ai.whatsapp.management`, all whitelisted):

| Function | Method | What it does |
|---|---|---|
| `get_setup_status` | GET | Setup checks (System Manager or Huf Admin) |
| `list_templates` | GET | One account's WhatsApp Templates (`gateway_name`, or an `account` you may see) |
| `create_template` | POST | Admin only. Creates a WhatsApp Templates row for `gateway_name`'s account. Its hook pushes it to Meta |
| `edit_template` | POST | Admin only. Edits a template on Meta under Meta's edit rules |
| `delete_template` | POST | Admin only. Deletes the row. `frappe_whatsapp` removes the template on Meta |
| `sync_templates` | POST | Admin only. Imports templates that exist on Meta but not in Huf (without pushing anything back to Meta) and refreshes status, category and id of existing ones, for one gateway's account. Returns `imported`, `updated`, `unchanged` |
| `create_template_draft` | POST | Needs the draft doctype's create permission or an admin role (the non-admin "request" path) |
| `approve_template_draft` / `reject_template_draft` | POST | Admin only |
| `list_template_drafts` | GET | One account's drafts |
| `send_template_message` | POST | `gateway_name` is required; needs write authority on that Gateway. Sends an approved template from the Gateway's own account. Allowed outside the 24h window |
| `send_text_message` | POST | `gateway_name` required, write authority. Sends free-form text. Refused with `window_closed` outside the window |
| `send_media_message` | POST | `gateway_name` required, write authority. Sends an image, document, audio or video by public link or public uploaded file. Refused with `window_closed` outside the window |
| `list_messages` | GET | Recent WhatsApp Messages of one gateway's account, newest first |
| `list_conversations` | GET | That account's recent messages grouped by counterparty number |

"Admin" means System Manager or Huf Admin. "Write authority on a Gateway" means write permission on that Gateway document, an admin role, or the `system.integrations.manage` capability; read access alone cannot send. Listing calls need `gateway_name` (or an `account` the caller may see: admins any, others only accounts of Gateways they can read); otherwise they return `{"success": false, "error": "gateway_required"}`. Nothing here uses `ignore_permissions`.

Template name rules: lowercase letters, digits and underscores only (`^[a-z0-9_]+$`). Category: `MARKETING` or `UTILITY` (`AUTHENTICATION` is not supported because Meta requires OTP button components). `language_code` is required.

**Agent tool actions** (`huf/ai/tools/whatsapp.py`): `list_templates` (read-only) and `create_template` (gated, see section 6). `delete_template` returns `template_in_use` for a template that has been sent, without touching Meta.

**Approval lifecycle**: the code does not enforce a state machine. A template is created in Meta by `frappe_whatsapp`. Its `status` field holds the value Meta reports, which Huf copies on `sync_templates` (that sync also imports templates that exist only on Meta, such as `hello_world`). The agent tool's `status` filter uses the values `PENDING`, `APPROVED` and `REJECTED`. Huf does not block sends of a template based on its status. Run a sync after Meta reviews a template, and check its status before relying on it as a fallback.


### 4.4 Rich templates (header, footer, buttons)

`create_template` (management API, console Create dialog, agent tool) accepts these optional parts besides the body. They map onto the `WhatsApp Templates` fields and `WhatsApp Button` child rows exactly as `frappe_whatsapp` defines them.

| Payload key | Doctype field | Notes |
|---|---|---|
| `template` (or `body`) | `template` | Required, up to 1024 characters. `{{1}}`, `{{2}}`, ... in order, no gaps |
| `sample_values` | `sample_values` | One example per body variable, comma separated (so examples cannot contain commas). Required when the body has variables |
| `header_type` | `header_type` | `TEXT`, `IMAGE` or `DOCUMENT`. `VIDEO` headers are not available in `frappe_whatsapp` and are rejected |
| `header` | `header` | TEXT header, up to 60 characters, at most one variable `{{1}}` |
| `sample` | `sample` | TEXT header with a variable: one example value. IMAGE/DOCUMENT: an `http(s)` URL (public, https outside tests) or the path of an uploaded File (`/files/...`). `frappe_whatsapp` uploads it to Meta for review |
| `footer` | `footer` | Up to 60 characters, no variables |
| `buttons` | `buttons` rows | List of `{type, text, ...}`: `QUICK_REPLY`; `URL` with `url` (a trailing `{{1}}` makes it dynamic and needs an `example` full URL); `PHONE_NUMBER` with `phone_number`. Mapped to `Quick Reply`, `Visit Website` (`url_type` Static or Dynamic, `example_url`) and `Call Phone` |

Limits enforced before anything is sent to Meta: button text 25 characters, at most 3 quick replies or 2 call-to-action buttons (URL plus phone) with at most one phone button, and quick replies and call-to-action buttons each grouped together. A bad request returns one structured error listing every problem:

```json
{"success": false, "error": "validation_failed", "message": "...",
 "errors": [{"field": "footer", "code": "too_long", "message": "..."}]}
```

**Sending with parameters.** `send_template_message` (and the tool's `send_template`, and the adapter in direct mode) take:

- `body_params`: strings for `{{1}}`... The count must match the template. Parameters cannot be empty or contain newlines, tabs or four or more spaces (Meta rejects them).
- `header_params`: one text string for a TEXT header variable, or one `{"type": "image|document", "link": "https://..."}` for a media header (`filename` is optional for documents). An IMAGE header with no link falls back to the template's own sample link.
- `button_params`: `[{"index": 0, "sub_type": "url", "text": "<suffix>"}]` for each dynamic URL button (`index` is the button's position, starting at 0). A bare string is the suffix of the button at that list position.

Bridge mode: plain body-only sends go through an Outgoing `WhatsApp Message`, which `frappe_whatsapp` sends. `frappe_whatsapp` cannot build header variables or dynamic URL parameters without a reference document, so sends that use `header_params` or `button_params` (or whose template has a dynamic URL button) are posted to Graph with the account credentials and mirrored into `WhatsApp Message` with the returned message id. There is still exactly one send.

Not available: `VIDEO` headers, `AUTHENTICATION` templates, carousel, flow, catalog and multi-product buttons, copy-code and other button types, and editing a template after it is created.

---

**Fallback template rules.** The fallback template is always sent without parameter values, so saving a Gateway is refused when the template (found for the linked WhatsApp Account) has any variable in its body, header or URL button, or a media header: "The fallback template can't have variables (it is sent without values). Pick a template with plain text." The check is skipped when `frappe_whatsapp` is not installed, no account is linked, or the template has not been synced yet (Health then warns with `fallback_template_unavailable` if Meta rejected or paused it).

**Do not use `frappe_whatsapp`'s "Fetch templates" button in Desk.** It overwrites Huf's mirrored template rows by template name only and bypasses Huf's guard. Use Huf's Sync instead.

**Warning:** templates imported before Huf managed them can still be edited in Desk, and that edit is a lossy re-push to Meta (rich parts are dropped), unless Huf has synced them first. Run Huf's Sync before anyone edits an older template in Desk.

### 4.5 Template states, drafts and editing

Huf keeps its own review state for every template (`WhatsApp Template State`, one row per template, named like the template row, for example `order_update-en_US`). It works on sites without `frappe_whatsapp` and stores what `frappe_whatsapp` drops: the rejection reason and recommendation, the quality score, a pending category change, and the last webhook event.

**Where the state comes from**
- Meta webhooks (`message_template_status_update`, `message_template_quality_update`, `template_category_update`) update the state as they arrive. Status events move the status (APPROVED, PENDING, REJECTED, PAUSED, DISABLED, IN_APPEAL, LIMIT_EXCEEDED, PENDING_DELETION, DELETED). FLAGGED, REINSTATED, LOCKED, ARCHIVED and UNARCHIVED only update the last event.
- Template sync reads `id, name, status, rejected_reason, quality_score, category, previous_category, correct_category, language, parameter_format, components, message_send_ttl_seconds`. It also refreshes the header, body, footer and buttons of existing rows when Meta's differ (an edit made in WhatsApp Manager); equal content is left alone.
- Every status change publishes the realtime event `whatsapp_template_status` with `{template, status, reason}`.
- The quality value is kept as raw JSON (Meta's exact shape is not documented) plus a derived `GREEN`, `YELLOW`, `RED` or `UNKNOWN`. A category change is pending when Meta's `correct_category` is set and differs from the current category.

**Drafts and approval.** `create_template_draft` (console) and the agent's `create_template` save a `WhatsApp Template Draft` with the same validation as a direct create. Nothing is sent to Meta. A System Manager or Huf Admin then approves or rejects it. Approval validates the payload again and submits it to Meta exactly once (status `Approved & Submitted`, with the created template recorded); a Meta refusal sets `Failed` with the error and the draft can still be approved again or rejected. Rejection never contacts Meta. Statuses: Draft, Pending Review, Approved & Submitted, Rejected, Failed. To let an agent submit without review, add the Integration Settings credential `auto_submit_templates` = `1` (together with `allow_whatsapp_management`). It is read server-side only.

**Editing.** `edit_template` sends the full components to `POST /{template-id}`. Meta allows an edit only while the template is APPROVED, REJECTED or PAUSED. An APPROVED template can be edited once per 24 hours and 10 times per 30 days (REJECTED and PAUSED are unlimited), and name and language cannot change. Huf checks these locally first and refuses without calling Meta; edits of APPROVED templates are logged in the state's `edit_log` to count the quota. An edited template goes back to PENDING review. Changing an image or document header needs a fresh media upload and is not supported here; edit those in WhatsApp Manager.

**WhatsApp Manager link.** Template details include `manager_url`, the WhatsApp Manager template list (`https://business.facebook.com/latest/whatsapp_manager/message_templates`), and the WhatsApp Business Account id as `business_id` for display. Meta documents no query parameters for this page, so the link cannot jump to a single template or account: sign in to the right business and find the template by name.

## 5. Agent tool

Actions: `send_message`, `send_media`, `send_template`, `list_messages`, `get_account_info`, `list_templates`, `create_template`.

The tool is bound to the gateway of the current run (the conversation channel `gateway:<name>`). `gateway_name` and `whatsapp_account` are not tool parameters and are discarded if supplied. A run that is not bound to an enabled WhatsApp gateway is refused (`gateway_context_required`); there is no default account. Sends need Gateway write authority for the run user; reads need read authority. `list_templates` lists only the gateway's own account.

- `list_messages` (`to` = the contact, `limit` 1-50, `cursor`) returns that contact's messages through the run gateway, newest first, with the wamid in `message_id` and a `next_cursor`.
- `send_message` is a free-form text send. It is **proactive** unless the run gateway's window for that number is open. A proactive send needs the gateway's "Agent may send outside the 24-hour window" setting, and is refused for opted-out contacts.
- `send_media` (`to`, `kind` image/document/audio/video, `link`, `caption`, `filename`) is a free-form send. It follows exactly the same proactive logic and flags as `send_message`.
- `send_template` is always allowed. It accepts `parameters`, `header_params` and `button_params` (see section 4.4).
- `create_template` needs the gateway setting "Agent may draft templates" (not the proactive one), accepts the header, footer and button fields of section 4.4, and saves a **draft** for human approval (section 4.5). `get_template_status` reports the review status, rejection reason, quality and draft state of a template or draft; `list_templates` rows include status and rejection reason.
- The tool never uses `ignore_permissions` and never switches the session user.
- `send_template`, `get_account_info` and the fallback path of `send_message` call the Graph API directly, using the `phone_number_id` and `access_token` of the run gateway's own integration. `send_message` logs to `WhatsApp Message` only when the bridge is not used and the app is installed.

---

## 6. Agent tool gating

Three per-gateway Check fields control privileged behaviour. They are read from the run gateway only and are off by default.

| Gateway field | Enables |
|---|---|
| `agent_allow_proactive` | Free-form sends outside an open window |
| `agent_allow_template_management` | `create_template` (as a draft); does not allow proactive sends |
| `agent_auto_submit_templates` | `create_template` submits straight to Meta (only together with template management) |

Rules:

- Any error while reading a flag fails closed.
- The LLM cannot enable a flag. Any `allow_proactive`, `allow_whatsapp_management` or `auto_submit_templates` argument in a tool call is discarded.

---

## 7. Media

**Inbound.** The adapter records each image, document, audio, video or sticker message as an attachment entry (media id, MIME type, filename, kind) in the event's raw payload. The text of the message is used as the agent input. The caption is used when present.

The bridge provides `download_media`, which enforces:

- per-kind size limits matching Meta's inbound limits, checked against both the declared and the streamed size: document 100 MB, image 5 MB, audio 16 MB, video 16 MB, sticker 500 KB
- MIME allowlist: `image/`, `audio/`, `video/`, `application/pdf`, `text/plain`, plus Office documents (`application/msword`, `application/vnd.openxmlformats-officedocument.*`, `application/vnd.ms-excel`, `application/vnd.ms-powerpoint`). SVG, HTML and executables are always rejected
- filename sanitised to `A-Z a-z 0-9 . _ -`, at most 100 characters

When the background job processes an event with an image, document, audio, video or sticker, it calls `download_media` (best-effort), saves a private File attached to the Gateway Event, and adds an `[Attachment saved: <url>]` note to the agent prompt. A failed or rejected download is logged and the text flow continues.

**Outbound.** The adapter declares `supports_media_reply = True`.

- `adapter.send_media(to, kind, link=..., media_id=..., caption=..., filename=...)`: `kind` is `image`, `document`, `audio` or `video`. Give exactly one of a public `link` or a Meta `media_id`. Captions are up to 1024 characters and are not allowed on audio. `filename` applies to documents. Direct mode posts the Graph `/messages` payload. Bridge mode inserts an Outgoing `WhatsApp Message` with `content_type` and `attach` (so only `link` is supported; `media_id` and `filename` are not).
- **Media links are checked before sending.** Meta downloads a `link` asynchronously after it accepts the send, so a dead, hotlink-protected (HTTP 403) or HTML-returning URL still gets a message id and is then silently never delivered. Huf therefore fetches the link first (https only, up to 3 redirects, every hop SSRF-checked, short timeout) and requires HTTP 200, a content type that matches the kind (never a web page) and the Meta size cap (image 5 MB, audio/video 16 MB, document 100 MB, sticker 100 KB static / 500 KB animated). A failure returns `media_link_unreachable`, `media_link_wrong_type` or `media_link_too_large` without calling Graph. Uploading the file (`file_url`) is the reliable path; it skips the link fetch entirely.
- Free-form media is subject to the same 24h window as text. A closed window raises `WhatsAppWindowClosed` (management API: `window_closed`). There is no template fallback for media.
- `GatewayReply.attachments` is honoured by the WhatsApp adapter: the first attachment (URL or media id) is sent with the reply text as its caption; for audio the text follows as a separate message. Other adapters ignore the field, and the agent reply pipeline does not produce attachments yet, so today media is sent through the explicit paths: the adapter, the management endpoint `send_media_message`, and the agent tool action `send_media`.
- Uploaded files must be public (`/files/...`) for Meta to fetch them. Private files are rejected with `invalid_file`.

### Fake Graph API

`huf/testing/fake_graph_server.py` is a real local HTTP server that implements the Graph endpoints Huf and `frappe_whatsapp` call (messages, message_templates, resumable sample upload, media lookup and download) and strictly validates request bodies against Meta's documented schema, including template review state and parameter counts. `test_whatsapp_fake_graph.py` points the WhatsApp Account `url` and an Integration Settings `graph_api_url` credential at it, so real `requests` calls are made. The `graph_api_url` credential and the `frappe.flags.whatsapp_test_media_hosts` media-host allowance are only honoured while `frappe.flags.in_test` is set; production always uses `graph.facebook.com` and the fixed media host allowlist. A schema violation recorded by the fake fails the test.

Remaining limits of the fake and of the feature: live Meta has not been exercised; the fake does not model Meta's own review decisions, rate limits or the 24h window; template edits after creation, `VIDEO` headers and non-text inbound opening the window are not supported.
