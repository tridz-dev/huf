# WhatsApp Embedded Signup ("Connect with Facebook")

Embedded Signup lets a customer connect a WhatsApp number from the setup wizard by logging in to Meta, with no copy and paste of IDs and keys. All code is in the repo; what remains is Meta configuration and Meta's review.

## Meta side (Tech Provider)

1. Create a Meta app of type Business, add the WhatsApp product, and complete Business Verification for the owning Business Manager.
2. Enroll the business as a Tech Provider and pass App Review for `whatsapp_business_management` and `whatsapp_business_messaging` (Advanced Access). This review is external and takes time.
3. Facebook Login for Business: add the site domains (the Huf site, and the Huf Cloud domain for broker mode) under Valid OAuth redirect URIs and Allowed domains for the JS SDK.
4. Create an Embedded Signup configuration (Facebook Login for Business, Configurations, Create, WhatsApp Embedded Signup). Choose the token type "Business integration system user access token" and the WhatsApp permissions. Copy the **Configuration ID**.
5. Set the app webhook (WhatsApp Business Account object) to the Huf callback URL and subscribe to `messages`, `message_template_status_update`, `account_update`, `phone_number_quality_update`.

## Modes

Set in Channels, Settings, Facebook signup (or the `Channel Embedded Signup Settings` single). Secrets are write-only.

| Mode | Who owns the Facebook app | Code exchange | Needs |
| --- | --- | --- | --- |
| `direct` | This site | This site calls `/<ver>/oauth/access_token` | app id, config id, app secret |
| `broker` | Huf Cloud | This site posts `{code, waba_id, phone_number_id}` to the broker | app id, config id (public values from Huf), broker URL, tenant id, broker API key |
| `broker_server` | This site, for tenants | `broker_exchange` exchanges for tenants | app id, config id, app secret, allowed tenants |

Self-hosted sites usually cannot be a Tech Provider themselves, so they use `broker` against the central Huf Cloud site, which runs `broker_server`.

### Flow (all modes)

1. Admin clicks Connect with Facebook; the FB JS SDK loads on click, `FB.login` opens Embedded Signup with the config id.
2. The browser receives the one-time `code` and a `WA_EMBEDDED_SIGNUP` message (waba_id, phone_number_id) from a `facebook.com` origin only.
3. The browser calls `huf.ai.channels.embedded_signup.complete_signup`. The server obtains the business token, subscribes the app to the WABA (`POST /<waba_id>/subscribed_apps`), registers the number (`POST /<phone_number_id>/register` with a 6-digit PIN; generated and returned once if you did not supply one) and creates or updates the WhatsApp Gateway through the same Integration Settings + Gateway documents the manual wizard writes. The wizard then jumps to the webhook step.

### broker_server tenants

Create a tenant key with the whitelisted `create_tenant_key(tenant_id, site_url)` (System Manager); the plaintext key is returned once and only its SHA-256 hash is stored in the `Embedded Signup Tenant` child row. Disable a tenant by unchecking `enabled`. Tenants call `POST /api/method/huf.ai.channels.embedded_signup.broker_exchange` with `X-Huf-Tenant: <id>`, `Authorization: Bearer <key>` and JSON `{code, waba_id}`. The response is `{access_token, webhook_signing_secret}`. The signing secret is derived per tenant (HMAC of the app secret); the real app secret is never sent. The broker's webhook forwarder must re-sign forwarded events with that secret, because tenants cannot see Meta's signature key.

## Security notes

- The business token is stored only in the Integration Settings Password field. It is never returned from `complete_signup`, never logged; errors are passed through `redact` and the app secret, code and PIN are scrubbed.
- `get_signup_config` returns only app id, config id, graph version and enabled. Admin only.
- `broker_exchange` requires HTTPS (checks `X-Forwarded-Proto`; bypassed only in developer mode), compares the key to the stored hash in constant time (also for unknown tenants), is rate limited per IP, and writes an `Embedded Signup Audit` row per exchange (tenant, outcome, WABA id; never a code or token).
- The browser only trusts `message` events from `https://*.facebook.com`.
- Broker URL must be https.
- The generated PIN is shown once in the wizard; store it, it is needed to re-register the number.
- Not covered here: Meta's review, the hosted Huf Cloud deployment, and forwarding webhooks to tenant sites.
