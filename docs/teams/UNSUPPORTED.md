# Microsoft Teams gateway: not supported in slice 1

An honest list of what this build does **not** do, with the reason. "Deferred" means planned for
a later slice in PLAN_v1 (section 3); it is not available today.

| Area | Status | Reason |
|---|---|---|
| Microsoft Graph (any call, any permission) | Not implemented | Slice 1 uses only the Bot Framework transport. No Graph consent, no Graph tokens |
| SSO / OIDC / OAuth (user sign-in with Microsoft, redirect URIs, `webApplicationInfo`) | Not implemented | Linking is a Huf-side login plus a signed single-use link. There is no Microsoft-side confirmation of the principal beyond the verified activity |
| Teams tabs, personal or channel | Not implemented | No tab or static-page code; the manifest has no `staticTabs`/`configurableTabs` |
| Message extensions (search, actions, link unfurling) | Not implemented | No `composeExtensions`; compose and message-action invokes are ignored |
| Task modules / dialogs | Not implemented | Only `adaptiveCard/action` invokes are handled |
| File upload/download in chat, generated reports, attachment ingestion | Not implemented | Attachments with a `contentUrl` are listed on the event but never downloaded; the bot sends no files; `supportsFiles` is false |
| Meetings (meeting bot, transcripts, recordings, in-meeting) | Not implemented | Not in scope |
| Reading messages without an @mention (RSC, `ChannelMessage.Read.Group`, `ChatMessage.Read.Chat`, change notifications) | Not implemented | Requires Graph/RSC. Channel and group messages are processed only when the bot is mentioned (personal chat always) |
| Multi-tenant bot (other organisations installing one Huf bot), per-tenant admin consent, tenant/site pairing handshake | Not implemented | Single-tenant app registration. The allowed-tenants list exists but a single-tenant bot only receives its home tenant's tokens; verify before relying on partner tenants. Tenant ownership is not proven by a typed GUID |
| Multiple Huf sites per tenant, site selection per conversation | Not implemented | One gateway = one site |
| National and sovereign clouds (GCC High, DoD, China) | Not supported | Endpoints, authority and issuer are fixed to the commercial cloud |
| Guest and external Entra users | Rejected with a message | Always refused; no mapping policy |
| Private and shared channels | Not tested, not supported | No installation-scope handling or documented behaviour. Manifest scopes are personal, team, groupChat only |
| Channel notifications to arbitrary channels, scheduled digests, broadcasts | Not implemented | Only private notifications to one linked user's personal chat. No scheduler job that posts messages |
| Agent tool `teams_send` and automation action | Not implemented | Use the whitelisted `send_teams_notification` method |
| Teams-SDK TypeScript relay / managed gateway / customer-hosted adapter | Not implemented | Direct mode inside Frappe only. Contract `teams-p0/1` is versioned so a relay could follow later |
| Activity feed notifications (Graph) | Not implemented | Needs Graph |
| Text preferences beyond `help/connect/status/disconnect` (quiet hours, opt-out, time zone, language) | Not implemented | No preference storage. No per-user notification controls; all text is English and not localised |
| Per-user or per-channel budgets and rate limits | Not implemented | Only the outbound adapter ceiling (20 messages/second declared) and the 100/60 s webhook rate limit |
| Flow human-approval cards (`approve_flow_run`) | Not implemented | Only Agent Execution Approval; PLAN v2 decision |
| Card actions other than Approve/Reject; card updates after delivery | Not implemented | The outbox supports a `card_update` kind but no caller enqueues it, and the delivered card activity id is not recorded automatically |
| Revoking pending approval cards when a user is disconnected | Partial | A revoked user cannot decide (identity no longer resolves) but their open Action Sessions remain `Open` until expiry |
| Retention/purge of Teams data | Not implemented | Only generic 30-day purge of Rejected Gateway Events exists. See SECURITY_AND_DATA.md |
| Resend of Dead outbound messages | Not implemented | No API or button; diagnostics text mentions resending, but there is no resend action |
| Custom help text | Not implemented | `help_text_override` is stored but ignored |
| Wizard Save draft / Back / per-step state, credential-expiry tracking, "enable production" summary | Not implemented | Wizard is a single scrolling page of seven sections plus diagnostics |
| Admin "switch approved site", "reconnect Microsoft access" | Not applicable | No SSO or multi-site |
| Slack-style `unmapped_policy = Use service user` for Teams | Intentionally not supported | Teams identity fails closed |
| Real-tenant verification of desktop/web/mobile card rendering | Not done | See REAL_TENANT_CHECKLIST.md |
| Legacy Outgoing Webhook | Unchanged, limited | Separate HMAC path, public channels only, synchronous reply; not extended |
| Email/UPN auto-mapping to a Huf user | Not implemented | Email, UPN and display name are never used as identity keys |

Known technical limits: text replies are sent as Markdown; replies are sent through a queue and
may arrive seconds after the request; there is no typing indicator; there is no streaming.
