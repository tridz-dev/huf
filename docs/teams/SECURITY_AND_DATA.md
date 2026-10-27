# Microsoft Teams gateway: security and data handling (slice 1)

Based on the code on `wp/teams-t15` merged with `feat/teams-p0` after the independent review fixes
(`ongoing/teams-p0/OPUS_TEAMS_REVIEW.md`). Open items are in KNOWN_ISSUES.md. Nothing here is a certification. The gateway has not been tested
against a real tenant (REAL_TENANT_CHECKLIST.md).

## 1. Trust boundaries

1. **Internet to Huf webhook.** Anyone can POST (the route is guest-accessible). Nothing is stored or
   executed until the Bot Framework JWT verifies: RS256 only; issuer must be `https://api.botframework.com`
   or the home tenant's Entra issuer (`login.microsoftonline.com/<tenant>/v2.0` or `sts.windows.net/<tenant>/`);
   signature against keys fetched from the issuer's OpenID metadata (https only, cached 24 h, forced
   refresh on unknown `kid` at most once per 60 s); `aud` must equal the `app_id` credential; `exp`/`nbf`
   with 300 s skew; the token `serviceurl` claim must equal the activity `serviceUrl`; for Bot Framework
   keys the `msteams` endorsement is required when present. Failure returns 401 with no detail. Tokens are
   never logged.
2. **Activity content is untrusted even after verification.** Tenant is checked against the allowlist
   (fail closed on missing or inconsistent tenant claims: every claim must be allowed) for messages, commands,
   install events and card actions. Filters run in priority order, stop at the first rejection and fail
   closed on exceptions (`filter_error`); a rejected event is stored as a Rejected Gateway Event
   (`tenant_not_allowed`) and gets no reply. A sender-supplied `huf_kind` field is deleted before use.
3. **Huf to Microsoft (outbound).** Only the stored conversation reference's `service_url` is used, after an
   SSRF check (https, port 443, host exactly `smba.trafficmanager.net` or suffix `.botframework.com` / `.teams.microsoft.com`; other `*.trafficmanager.net` hosts are refused,
   no IPs, no userinfo, no encoded or dot segments). Redirects are not followed. The client secret is sent
   only to `login.microsoftonline.com`.
4. **Person to Huf identity.** A Teams person (tenant GUID + Entra object id) maps to a Huf user only through
   a `Linked` Gateway Identity Link. No fallback to the gateway Run as user, to email, UPN or display name.
   Guests, external users, senders without an Entra object id or with inconsistent tenant claims, and Guest and Administrator Huf accounts are refused (Administrator only via admin link). Self-linking is two-way: the web confirmation creates a `Pending` link (never resolves a user) and the same Teams person (tenant + object id) must click Yes on a card in their personal chat; No revokes. If the card cannot be queued the pending link is revoked. Link URLs are never posted in channels or group chats.
5. **Approval click.** The clicker is taken only from the verified activity, never from card data. The card
   carries only an opaque Teams Action Session name. The session must match gateway, tenant and conversation;
   the decision runs under `frappe.set_user(clicker)` so Huf's own approval permission checks apply.
6. **Admin APIs.** System Manager or Gateway write permission. `send_teams_notification` also lets a user
   notify themselves.

## 2. What is stored

| Data | Where | Content and protection |
|---|---|---|
| Credentials | Integration Settings > Credentials | `app_id`, `app_password`, `tenant_id`; password fields encrypted by Frappe. Never in the manifest, diagnostics or support bundle (only presence is reported; the bundle renames `app_password` to `app_secret`) |
| Gateway Event | `Gateway Event` | Per accepted or rejected activity: sender (Entra id), conversation id, **message text in clear**, and `raw_payload` where only keys named authorization, token, secret, signature, api_key, password and similar are replaced by `[redacted]`. The activity body (names, text, tenant ids, serviceUrl) is stored. Bearer headers are not stored. Commands answered by the Teams filter (help/connect/status/disconnect) and install/uninstall events return before an event is inserted |
| Teams Conversation Reference | doctype | gateway, tenant, base conversation id, type, `service_url`, team/channel ids, user Entra id (personal chats), bot id, installed flag, last seen. Needed for proactive sends |
| Teams Outbound Message (outbox) | doctype | Full outbound activity as JSON, including reply text and cards, after `redact_payload` (masks keys such as token/secret/password/authorization and Bearer/JWT-looking strings). **Message text, private answers and connect links are stored.** Plus status, attempts, `last_error` (scrubbed, max 500 chars), provider message id |
| Gateway Identity Link | doctype | gateway, provider, tenant (`team_id`), Entra id (`external_id`), Huf user, state (`Pending`, `Linked`, `Revoked`), source, display label (Teams display name, max 80 chars), linked_at, linked_by. Revoked rows are kept |
| Teams Action Session | doctype | gateway, kind, state, expiry, intended user, tenant, base conversation id, payload (approval name, or the link name for kind `idlink`), decided_by, decision, card activity id |
| Agent Run / Flow Run | existing | `requester_user`, `requester_external_id` (Entra id), `gateway`, `gateway_event` are written on success |
| Redis | cache | Bot access token (until about 5 min before expiry), JWKS, nonces and throttles (ROUTES_AND_CONFIG.md section 5) |

The confirmation card is stored in the outbox like any card (it carries only the opaque session name).

Link tokens are stateless HMAC-SHA256 values signed with the site `encryption_key`, payload = gateway,
tenant, Entra id, display name, expiry, nonce. They are not stored in the database; the nonce is in
Redis for 10 minutes and consumed on confirm. The token is visible in the link URL and therefore in
the outbox row and Teams chat history.

## 3. Retention (what is NOT implemented)

- Only one purge exists: generic daily deletion of `Rejected` Gateway Events older than 30 days.
- No retention or purge for: successful Gateway Events and their message text, Teams Outbound Messages
  (including `Sent`), Teams Conversation References, Teams Action Sessions (expired sessions stay `Open`
  or `Expired`), revoked identity links, Agent/Flow Run links.
- No data-subject export or delete command. "Disconnect" revokes the link only; it does not delete the
  Teams person's stored events, references or outbox rows.
- An administrator must delete rows manually (REAL_TENANT_CHECKLIST.md section 8) until a retention
  policy is built. Define the policy with the data owner first (SPEC section 22).

## 4. Secret handling

- The client secret is entered once in Credentials and is encrypted at rest. It is never rendered back,
  returned by APIs, written to logs, exception text, outbox errors or diagnostics.
- Errors from Microsoft carry only the HTTP status and a sanitised error code.
- The bot token cache in Redis holds a live bearer token; protect Redis as you would the secret.
- Rotation: create a new secret in Entra, update `app_password`, restart workers. The token cache entry
  expires on its own; a 401 from the connector forces one refresh. Huf cannot warn about secret expiry.
- The self-link signing key is the site `encryption_key`; rotating it invalidates outstanding links.
- Back up the site only with the encryption key stored separately.

## 5. Known limitations and residual risks

| ID | Risk | Detail |
|---|---|---|
| R1 | Forwarded link (mitigated) | The signed token fixes the Teams person, not the Huf user, so any logged-in Huf user who opens an unused link can start a link. Since the review fixes the link stays Pending until that Teams person confirms in their personal chat, and the page shows the tenant GUID and marks the display name untrusted. A person who clicks Yes on a card they did not expect would still link; the card names the Huf user. Not yet tested against a real tenant |
| R2 | Install filter tenant check (fixed) | The install/uninstall filter now defaults to `teams_tenant.is_tenant_allowed` (fail closed); a foreign-tenant install is a Rejected Gateway Event and creates no reference (bench E2E S5b) |
| R3 | Content at rest | Message text, answers (including private ones), links and cards are stored in Gateway Event and the outbox without retention limits |
| R4 | Revocation is partial | Revoking a link or disabling the Huf user stops new runs, card clicks and personalized sends at once, but does not close pending Action Sessions or cancel queued outbox rows |
| R5 | Private routing is heuristic | "Private when records touched" is based on tool names outside a short allowlist; it cannot tell whether a tool output was sensitive. Choose "Always private" for sensitive deployments. Source snippets and record titles are inside the answer text, which is withheld, but the channel still shows the neutral acknowledgement and the fact a question was asked |
| R6 | Admission defaults | Gateway `direct_policy` and room policies default to Allow list and `Open` cannot be saved (KNOWN_ISSUES.md D1). Linking is the identity gate, not authorization to use every agent. Linking is the identity gate, not authorization to use every agent |
| R7 | Dead and Failed messages | After 6 failed attempts the outbox row is `Dead`; a permanently failed row is `Failed`. Neither is retried and there is no resend tool. Diagnostics lists up to 20 |
| R8 | Single-tenant only | Tenant ownership is not proven by anything other than the verified token and the configured tenant id |
| R9 | Legacy Outgoing Webhook | A separate HMAC path remains and is unchanged. Disable it if unused |
| R10 | Rate limiting | The webhook is limited per gateway name (100 per minute); unverified requests above that return a rate-limit error before verification, so a flood can delay legitimate Microsoft calls to the same gateway |
| R11 | No real-tenant evidence | Guest-account marker, mobile/desktop card rendering, private/shared channels and Markdown behaviour are unverified |
| R13 | Duplicate sends | A POST that succeeded but timed out is retried as transient and the Bot Connector has no idempotency key, so a message can arrive twice |
| R14 | Guests of the host tenant | Detection is heuristic (no roster check); see KNOWN_ISSUES.md |
| R12 | Manifest | Privacy and terms URLs point at `<site>/privacy` and `<site>/terms`, which Huf does not serve; icons are generic placeholders; schema 1.19 pinned offline |

## 6. Reporting and diagnostics

`teams_support_bundle` returns versions, counts, timestamps, rejection reasons, outbox counts, up to 20
dead-letter names with clipped errors and the number of linked users. It contains no message text,
tokens or credential values, and passes through the same redactor as the outbox. Share it with support
instead of Gateway Event exports.
