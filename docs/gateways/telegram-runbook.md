# Telegram Gateway Runbook

Behaviour is taken from code; file references name the source of truth. Companion docs:
`docs/gateways/whatsapp-runbook.md` (WhatsApp operations) and `docs/gateways/telegram-admin-cockpit.md`
(owner/admin cockpit design). Never put a bot token or webhook secret in this document, chat, tickets or logs.
Placeholders used below: `<BOT_TOKEN>`, `<WEBHOOK_SECRET>`, `<host>`, `<Gateway name>`.

Status labels: **wired** = reachable from a running path; **not wired yet** = code exists but nothing in the
product calls it; **off by default** = wired, but disabled unless configured.

Core modules: `huf/ai/gateway_adapters/telegram.py` (adapter, credentials), `telegram_client.py` (Bot API client,
`ALLOWED_UPDATES`), `telegram_hooks.py` (hook registration), `telegram_*_hooks.py` (per-feature hook wiring),
`huf/ai/telegram_admin.py` and `telegram_management.py` (cockpit and gateway management), `huf/ai/tools/telegram.py`
(agent tool actions).

## 1. What Telegram supports today

Compared with WhatsApp (`docs/gateways/whatsapp-runbook.md`). "Yes" means implemented in the Telegram modules.

| Capability | Telegram | WhatsApp | Notes / source |
|---|---|---|---|
| Text in/out | Yes | Yes | `telegram_inbound.py`, `telegram_pipeline.py` |
| Reply splitting | Yes | Yes | `make_parts` in `telegram_pipeline.py` |
| Formatting | Yes, HTML parse mode | Yes | `telegram_format.py`; pipeline uses `MODE_HTML` |
| Media in | Yes (photo, document, audio, video, voice, sticker, animation, etc.) | Yes | `media_refs` and `render_non_text` in `telegram_inbound.py`; saved via `media_save` hook |
| Media out | Yes: photo, document, voice, audio, video, animation, sticker, media group, location, contact | Yes | Tool actions in `tools/telegram.py`; upload limits 10 MB photo, 50 MB file |
| Voice out (agent voice reply) | Yes, Ogg/Opus; modes Off, Voice only, Text and voice | Yes | `telegram_voice.py`; gateway field `voice_reply_mode`; needs ffmpeg |
| Voice in | Voice notes arrive as media refs | Yes | No transcription step found in the Telegram modules (not verified) |
| Reactions | Inbound `message_reaction` parsed; outbound `set_reaction` tool | Partial | `supports_reactions=True` in adapter capabilities |
| Typing indicator | Yes, `sendChatAction typing`, best effort | Yes | `send_typing` in `telegram_pipeline.py`; gateway field `typing_indicator` |
| Inline buttons | Yes: callback, url, web_app, switch_inline, copy_text, login_url; reply keyboards | Yes | `telegram_buttons.py`, `telegram_keyboards.py` |
| Edit in place | Yes: `edit_message_text`, caption, reply markup | Partial | `supports_edit=True` |
| Streaming replies | **Off by default**; private chats only; `frappe.conf.huf_telegram_streaming` | No | `telegram_stream.py`, `telegram_stream_hooks.py` |
| Inline mode (`@bot query`) | Resolver registry; default article only | No | `telegram_inline.py`; inline results are wired, see the Run button below |
| Inline "Run" button | **not wired yet**: the default resolver builds a Run button, but no handler runs the agent | No | `default_resolver` and `RUN_CALLBACK_PREFIX` in `telegram_inline.py`; "spec only" in its docstring |
| Guest mode (`guest_message`) | Yes: `telegram_guest.py`, admitted to an agent by an Open policy | No | Limits in section 6 |
| Groups: join requests and Guard | Yes: `chat_join_request` handling with pairing codes and a join policy hook | Group access n/a | `telegram_groups.py`; `register_join_policy` |
| Group addressing | Yes: groups need @mention, reply to bot, or `/cmd@bot`, when `mention_required` is set | n/a | `is_addressed_to_bot` in `telegram_threads.py` |
| Forum threads | Yes: `message_thread_id` used for reply target | No | `telegram_threads.py`, `forum_thread_id` in pipeline |
| Business ("Secretary") | Observe-only by default; `ignore`, `observe`, `draft`, `reply` policies | No | `telegram_business.py`; see below |
| Bot-to-bot loop guard | Yes: drops bot senders unless allow-listed; hop and rate caps | No | `telegram_loop_guard.py` |
| Commands | Yes: `setMyCommands` per scope and language, ephemeral flag | No | `telegram_commands.py` |
| Admin cockpit | Yes: private-chat commands, signed buttons, audit | No | `telegram_admin.py`; see `telegram-admin-cockpit.md` |
| Mini App auth | Yes: initData validated, 15 min bearer token | No | `telegram_miniapp.py`; `telegram_admin.telegram_miniapp_auth` |
| Read receipts | Adapter-level `mark_read_typing` hook | Yes | `telegram_hooks.py` provider hooks |

### Business (Secretary) mode

- Updates `business_connection`, `business_message`, `edited_business_message` and
  `deleted_business_messages` are in `ALLOWED_UPDATES`.
- Default policy is `observe`: messages are recorded, never answered. Edits and deletions are only recorded.
- `draft` sends a proposed reply to the owner for approval. **Not wired yet:** `draft` needs a producer
  registered with `register_draft_producer` in `telegram_business.py`. Nothing calls it, so draft falls back.
- `reply` (auto-reply) is downgraded to `observe` unless the connection is enabled and holds `can_reply`.
- Own messages, bot-sent messages and bot senders never trigger a policy.

### Agent tool actions (`huf/ai/tools/telegram.py`)

The dispatch table exposes these actions to agents:

- Sending: `send_message`, `reply_to_message`, `send_photo`, `send_document`, `send_voice`, `send_audio`,
  `send_video`, `send_animation`, `send_sticker`, `send_media_group`, `send_location`, `send_contact`.
- Chat and message control: `set_reaction`, `send_chat_action`, `edit_message_text`, `edit_message_caption`,
  `edit_message_reply_markup`, `delete_message`, `pin_message`, `unpin_message`, `forward_message`, `copy_message`,
  `answer_callback_query`, `get_chat_info`, `get_me`.
- Gateway-blocked (refused when called through a gateway): `set_webhook`, `delete_webhook`, `get_updates`.
  Use the management functions in section 2 instead.

## 2. Setup

### 2.1 BotFather

1. In Telegram, open `@BotFather` and run `/newbot`. Save the token; it is the value of the `token` credential.
   It has the form `<BOT_TOKEN>` in this document. Do not paste it into chat.
2. Choose which modes to enable. The bot only receives the update types it is subscribed to (section 2.4).
   - **Bot-to-Bot Communication Mode**: needed only if other bots must reach this bot. Off by default; when on,
     the loop guard (section 6) is the only protection, so keep it on.
   - **Business Mode** (`/setbusiness` or the Business settings): needed for Secretary features. Without it no
     `business_*` updates arrive. The bot stays observe-only unless a policy is changed in code.
   - **Guest mode**: needed for `guest_message` updates. Without it, guest updates never arrive.
   - **Inline mode** (`/setinline`): needed for `@bot` inline queries.
3. **Group privacy** (`/setprivacy`): when enabled (default), the bot sees only commands, replies to its own
   messages and mentions in groups. Disable it only if the bot must read all group messages. The gateway
   addresses groups by mention anyway (`mention_required`), so keep privacy on unless needed.
4. **Commands** (`/setcommands`): optional. The gateway publishes commands through `setMyCommands` via
   `telegram_commands.set_commands` (scopes `default`, `all_private_chats`, `all_group_chats`, and others;
   max 100 commands, names `a-z 0-9 _` up to 32 characters, descriptions 1 to 256 characters).

### 2.2 Integration Settings credentials

Store credentials in the gateway's integration settings, never in the Gateway record text.

| Key | Required | Purpose | Source |
|---|---|---|---|
| `token` | Yes | BotFather token; used for all Bot API calls | `telegram.py` credential schema |
| `webhook_secret` | Yes | Sent as Telegram's `secret_token`; checked against the `X-Telegram-Bot-Api-Secret-Token` header | `telegram.py` (`WEBHOOK_SECRET_HEADER`) |
| `bot_allowlist` | No | Comma-separated bot ids allowed to talk to this bot (bot-to-bot) | `telegram_loop_guard.parse_allowlist` |
| `bot_max_hops` | No | Consecutive bot messages allowed in a chat or thread before cut-off; default 3 | `telegram_loop_guard.py` |
| `bot_rate_cap` | No | Bot messages allowed per chat and bot per 60 s; default 5 | `telegram_loop_guard.py` |

The cockpit reads `token` from the same integration settings (`telegram_admin.py`). Rotate `webhook_secret` by
changing it in settings and calling `set_webhook` again (section 2.4).

### 2.3 Create the Gateway

1. Create a Gateway with provider **Telegram** and link the integration settings that hold the credentials above.
2. **Direct-message policy**: set to **Pairing** (recommended). A stranger who messages the bot gets a pending
   pairing request, and the triggering message is not executed. Choices in `gateway.json`:
   Disabled, Pairing, Allow list, Open. `Open` admits anyone and should be used only for guest-style bots.
3. **Execution user**: the Frappe user that agent runs execute as. It must hold the **Huf Gateway User** role.
   `gateway.py` (`_validate_execution_user_role`) rejects the save otherwise with
   `execution_user '<user>' must have one of these roles: Huf Gateway User`. Do not use Administrator
   (operator guidance; the role check alone does not block it).
4. Set **Room policy**, **Room sender policy** and **Require mention in rooms** (default on) for group use.
5. Optional: voice replies (`voice_reply_mode`, needs ffmpeg on the worker host), typing indicator, and
   pairing TTL (`pairing_ttl_minutes`, default 60).
6. Enable the gateway. Disabled gateways answer the webhook with 403 (section 7).

### 2.4 Webhook

Webhook URL form:

```
https://<host>/api/method/huf.ai.gateway_webhook.handle_gateway_webhook?gateway_name=<Gateway name>
```

Set it with the secret and the allowed update list. `telegram_management` builds the URL with
`_webhook_url`; the call is:

```
setWebhook url=<URL above>, secret_token=<WEBHOOK_SECRET>,
          allowed_updates=ALLOWED_UPDATES   (huf/ai/gateway_adapters/telegram_client.py)
```

- `ALLOWED_UPDATES` includes `message`, `edited_message`, `callback_query`, `inline_query`,
  `chosen_inline_result`, `chat_join_request`, `chat_member`, `my_chat_member`, `message_reaction`,
  `message_reaction_count`, `channel_post`, the four `business_*` types, `stopped_message_generation` and
  `guest_message`. If a webhook was set earlier with a shorter list, guest and business updates never arrive.
  Re-set it.
- Telegram allows **one webhook per bot**. A second gateway or tool pointed at the same bot replaces it.
- Tunnels rotate: when the host, tunnel or port changes, call `setWebhook` again with the new URL. The old URL
  receives nothing.
- Telegram does not verify a GET challenge the way WhatsApp does. Confirm with `get_webhook_info` (the health
  check reads `getWebhookInfo`, `telegram_health.check_webhook`), which reports the URL, pending update count,
  last error and whether `allowed_updates` covers `ALLOWED_UPDATES`.

## 3. Pairing and access

- Unknown direct senders under the **Pairing** policy get a pairing code (`pairing_ttl_minutes`). The pending
  request never runs the agent. An approved Gateway Access Entry is needed before messages run.
- Groups: `chat_join_request` updates go to the join policy (`telegram_groups.py`). A join request can be
  approved, declined, or answered with a pairing code. Pairing in a direct chat never grants room access.
- Room senders follow `room_sender_policy` (Allow list or Open).
- Consent (STOP/START) is not implemented for Telegram. The WhatsApp opt-out path is WhatsApp only
  (`whatsapp-runbook.md` section 6). `consent_required()` in `telegram_hooks.py` returns no consent handling.
- Bot senders are not admitted by default; section 6 describes the allowlist.

## 4. Agent button format and tool actions

The agent is told how to attach buttons. The text comes from `AGENT_INSTRUCTIONS` in
`huf/ai/gateway_adapters/telegram_buttons.py` (copy it when you change the prompt):

```
```telegram-buttons
{"rows": [[{"text": "Yes", "callback": "yes"}, {"text": "Site", "url": "https://..."}]], "edit": false, "once": true}
```
```

- Button kinds: `callback` (id at most 46 bytes), `url`, `web_app`, `switch_inline`, `copy_text`, `login_url`.
- Alternatives: `reply_keyboard` (`rows`, `one_time`, `resize`, `placeholder`) or `remove_keyboard: true`.
- Limits: 8 buttons per row, 10 rows.
- A press reaches the agent as `[button: <text>]`.
- Callback data is signed (section 5); the cockpit's own buttons use the same signing.

## 5. Admin cockpit

Full design, threat model and command table: `docs/gateways/telegram-admin-cockpit.md`. Operator summary:

1. A signed-in Frappe user calls `create_binding_code(gateway, role_scope)` (POST, whitelisted). It returns
   `BIND-XXXXXXXXXX`. Guest and Administrator cannot bind.
2. In a private chat with the bot, `/start BIND-XXXXXXXXXX` (or the deep link) creates a
   `Telegram Admin Binding`. The code is single use, expires in 10 minutes and is stored hashed.
3. Commands (private chats only): `/me`, `/find`, `/open`, `/approvals`, `/digest`, `/audit` (Admin scope),
   `/help`, `/unbind` (confirmed). Scopes are Viewer, Operator and Admin.
4. Writes follow confirm and audit: button press, then a confirm message with a 5 minute nonce, then the
   action runs as the bound user with `apply_workflow`, and a `Telegram Admin Audit` row is written.
5. The daily digest is wired: `send_daily_digests` is in the daily scheduler in `huf/hooks.py`. (The cockpit
   design doc still says registration is pending; the code has it registered.)
6. Revoke a binding with `/unbind` or `revoke_binding(name)`. A binding does not add the user to the gateway
   access list, and the cockpit does not run agents.

Residual risks (from the design doc, still open):

- Nonce and code claims use Redis `SET NX` when available; the local fallback is best effort get-then-set.
- Captured initData can mint Mini App tokens for up to 10 minutes, and whoever holds it is already that
  Telegram client.
- `/find` uses `like` on name and title only; large tables can scan.
- Workflow approvals cover `Workflow Action` only. Non-workflow submit and cancel are not offered.

## 6. Operating notes

- **Rate limits**: the adapter declares 30 messages per second (`max_outbound_messages_per_second`). Group
  and private limits from Telegram still apply.
- **Flood control**: a `429` or `retry_after` is retryable. `TelegramBotClient.call` retries up to
  `max_flood_retries` times when the wait is short (`max_flood_wait`). The send pipeline waits `retry_after + 1 s`
  before the next attempt (`classify` in `telegram_pipeline.py`). Otherwise the default exponential backoff applies.
- **Blocked bot**: a 403 "bot was blocked by the user" or "user is deactivated" is classified `blocked`. The reply
  is not retried, and the event note reads "Recipient blocked the bot: reply not sent".
- **Chat not found**: classified `chat_not_found`; not retried.
- **Opt-out**: there is no STOP/START handling for Telegram. A user who blocks the bot is handled as above.
- **Guest limits** (`telegram_guest.py`): 5 messages per guest per 60 s, 20 per chat per 60 s. Over-limit
  guests get "You're sending messages too quickly." A denied guest is told once per hour.
- **Bot-to-bot loop guard** (`telegram_loop_guard.py`): bot messages are dropped unless the sender id is in
  `bot_allowlist`. An allowed bot is cut off after `bot_max_hops` consecutive bot messages in a chat or thread
  (a human message resets it), and above `bot_rate_cap` per 60 s. Our own bot id is never admitted. State lives
  in the Frappe cache, so counts are approximate.
- **Logs and errors**: `TelegramBotClient.redact` removes the token and its secret half from error text and
  logs (`redact_token` in `telegram_client.py`). Do not add logging that echoes request URLs, which contain the
  token.
- **Voice replies**: need ffmpeg with libopus on every worker host (`ffmpeg -encoders | grep libopus`). Replies
  over 1500 characters are text only.

## 7. Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| Webhook POST returns **401** `Provider verification failed` | `X-Telegram-Bot-Api-Secret-Token` does not match the `webhook_secret` credential | Set the webhook again with the current `secret_token`, or correct the credential. Failed checks set `last_signature_failure_at`. |
| Webhook POST returns **403** `Gateway is disabled` | Gateway `is_enabled` is off | Enable the gateway. |
| Webhook POST returns **413** | Body larger than the webhook limit | Check for unusual payloads; not expected for Telegram. |
| No updates arrive, webhook shows no error | Webhook URL points elsewhere (tunnel rotated) or another webhook replaced it | Call `getWebhookInfo`, then `setWebhook` with the current URL. |
| Updates arrive but guest or business messages do not | `allowed_updates` was set with a short list | Re-set the webhook with `ALLOWED_UPDATES`. Health check `allowed_updates_ok` shows the gap. |
| Pairing code sent but nothing happens after approval | Pairing creates a pending request; the triggering message never runs | Send a new message after approval. |
| No pairing code | Direct-message policy is not Pairing, or `pairing_reply_enabled` is off | Check the gateway policy fields. |
| Group message ignored | Bot not mentioned, not replied to, or group privacy blocks it | Mention `@<bot>` or reply to the bot. |
| Inline "Run" button does nothing | Not wired yet: no handler runs the agent for `inl:run:` | Expected today. Do not promise it to users. |
| No popup for an inline result | Inline mode not enabled in BotFather, or no resolver registered | Enable inline mode; register a resolver. |
| Save fails: `execution_user ... must have one of these roles: Huf Gateway User` | Run-as user lacks the role | Give the user the Huf Gateway User role, or pick another user. |
| Business reply never sent | Policy is `observe` (default), or draft producer not registered | Expected unless a policy and producer are configured. |
| Streaming not used | `huf_telegram_streaming` is unset, or chat is a group | Expected (off by default; private chats only). |
| Voice reply sent as text | ffmpeg or libopus missing, or TTS model missing | Install ffmpeg with libopus on the worker host; see WhatsApp runbook section 8 for the same check. |
| `Recipient blocked the bot: reply not sent` | The user blocked the bot | No action; the user must unblock. |
| `Flood control` in logs | Telegram rate limit (`retry_after`) | Retried automatically; if persistent, reduce burst traffic. |

## 8. Testing

Unit and adapter tests live in `huf/ai/tests/test_telegram_*.py`. The fake Bot API is
`huf/ai/tests/telegram_fakes.py` (`FakeTelegram`-style `http_post` and `http_get` injection, fixed
`TOKEN` and `SECRET` values, fixtures under `huf/ai/tests/fixtures/telegram/`).

Run one module through the bench test runner:

```
cd <bench path>
bench --site <test site> run-tests --app huf --module huf.ai.tests.test_telegram_loop_guard
```

Run all Telegram suites:

```
bench --site <test site> run-tests --app huf --module huf.ai.tests.test_telegram_adapter_core
bench --site <test site> run-tests --app huf --module huf.ai.tests.test_telegram_pipeline
# repeat for each test_telegram_*.py module, or run the whole app: bench --site <test site> run-tests --app huf
```

The CI backend job (`.github/workflows/server-tests.yml`) runs `bench --site test_site run-tests --app huf`.
`scripts/huf-verify.sh` wraps the same command with `--module`.

Repo guardrail before any commit: `python3 scripts/check_repo_layout.py`.
