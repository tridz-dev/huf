# Telegram Gateway Runbook

Behaviour is taken from code; file references name the source of truth. Companion docs:
`docs/gateways/whatsapp-runbook.md` (WhatsApp operations), `docs/gateways/telegram-admin-cockpit.md`
(owner/admin cockpit design) and `docs/gateways/telegram-miniapp-api.md` (Mini App endpoints).
Never put a bot token or webhook secret in this document, chat, tickets or logs.
Placeholders used below: `<BOT_TOKEN>`, `<WEBHOOK_SECRET>`, `<host>`, `<Gateway name>`, `<BIND-CODE>`.

Status labels: **wired** = reachable from a running path; **not wired** = the setting or code exists but
nothing on the runtime path reads or calls it; **off by default** = wired, but disabled unless configured.

Core modules: `huf/ai/gateway_adapters/telegram.py` (adapter, credentials), `telegram_client.py` (Bot API client,
`ALLOWED_UPDATES`), `telegram_hooks.py` (hook registration; imports one `telegram_*_hooks.py` per feature),
`huf/ai/telegram_admin.py` and `telegram_management*.py` (cockpit and management API),
`huf/ai/tools/telegram.py` (agent `telegram` tool) and `huf/ai/tools/telegram_admin_tools.py` (agent
`telegram_admin` tool), `huf/ai/telegram_templates.py` (message templates), `huf/ai/telegram_guard.py`
(join policy and Guard), `huf/ai/gateway_adapters/telegram_business*.py` (Secretary mode).

## 1. What Telegram supports today

Compared with WhatsApp (`docs/gateways/whatsapp-runbook.md`). "Yes" means implemented in the Telegram modules.

| Capability | Telegram | WhatsApp | Notes / source |
|---|---|---|---|
| Text in/out | Yes | Yes | `telegram_inbound.py`, `telegram_pipeline.py` |
| Reply splitting | Yes | Yes | `make_parts` in `telegram_pipeline.py` |
| Formatting | Yes, HTML parse mode by default | Yes | `telegram_format.py`; gateway field `telegram_parse_mode` |
| Media in | Yes: photo, document, audio, video, voice, video note, sticker, animation; rich descriptions (section 4.3) | Yes | `telegram_inbound.py` (`media_refs`, `render_non_text`); saved via `media_save` hook |
| Media out | Yes: photo, document, voice, audio, video, animation, sticker, media group, location, contact, video note, venue, dice, poll, checklist | Yes | Agent `telegram` tool (section 9); agent `telegram-media` block (section 4.2) |
| Voice out (voice replies) | Yes, Ogg/Opus; gateway field `voice_reply_mode` (Off, Voice only, Text and voice) | Yes | `telegram_voice.py`; needs ffmpeg with libopus; TTS via the agent's `tts_model` (section 16) |
| Voice in | Yes: voice notes, audio and video notes are saved and transcribed | Yes | Transcription is provider-neutral: `media_prep.prepare_media_for_agent`, called by `gateway_service` (see `telegram_voice.py` docstring) |
| Reactions | Inbound `message_reaction` parsed; outbound `set_reaction` tool action | Partial | `supports_reactions=True` in adapter capabilities |
| Typing indicator | Yes, `sendChatAction typing`, best effort | Yes | `send_typing` in `telegram_pipeline.py`; gateway field `typing_indicator` (default on) |
| Inline buttons | Yes: callback, url, web_app, switch_inline, copy_text, login_url; reply keyboards | Yes | `telegram_buttons.py`, `telegram_keyboards.py` (section 4.1) |
| Edit in place | Yes: `edit_message_text`, caption, reply markup; buttons with `"edit": true` | Partial | `supports_edit=True` |
| Streaming replies | **Off by default**; private chats only; controlled by the Gateway field `telegram_streaming` only | No | `telegram_stream.py` `streaming_enabled` (section 16) |
| Inline mode (`@bot query`) | Resolver registry; default resolver returns article results | No | `telegram_inline.py`; gateway field `telegram_inline_enabled` is **not read** (section 17) |
| Inline answer button | Signed `inl:go:<digest>` button on the placeholder; press starts the answer run when no `chosen_inline_result` arrived (idempotent per `inline_message_id`) | No | `handle_inline_callback` in `telegram_inline.py` |
| Guest mode (`guest_message`) | Yes: `telegram_guest.py`, admitted to an agent by an Open policy | No | Limits in section 11 |
| Groups: join requests and Guard | Yes: `chat_join_request` handling; join policy Queue, Decline or Agent (section 15); optional Guard Mini App | Group access n/a | `telegram_groups.py`, `telegram_guard.py`, `register_join_policy` |
| Group addressing | Yes: groups need @mention, reply to bot, or `/cmd@bot`, when `mention_required` is set | n/a | `is_addressed_to_bot` in `telegram_threads.py` |
| Forum threads | Yes: `message_thread_id` used for reply target; forum topic actions for agents | No | `telegram_threads.py`, `forum_thread_id` in pipeline |
| Business ("Secretary") | Yes: policies Ignore, Observe (default), Draft, Reply; owner approves drafts (section 14) | No | `telegram_business.py`, `telegram_business_agent.py` |
| Bot-to-bot loop guard | Yes: drops bot senders unless allow-listed; hop and rate caps | No | `telegram_loop_guard.py` (caps read from Integration Settings, section 11) |
| Message templates | Yes: saved text, variables, media and buttons (section 10) | Yes (WhatsApp templates are a different, Meta-approved mechanism) | `telegram_templates.py`, doctype `Telegram Message Template` |
| Commands | Yes: `setMyCommands` per scope and language, ephemeral flag | No | `telegram_commands.py` |
| Admin cockpit | Yes: private-chat commands, signed buttons, audit (section 5) | No | `telegram_admin.py`; see `telegram-admin-cockpit.md` |
| Agent admin actions | Yes, gated: group admin, bot profile, business (section 9.2) | No | `telegram_admin_tools.py`; off by default |
| Mini App auth | Yes: initData validated, 15 min bearer token | No | `telegram_miniapp_api.py`; `telegram_admin.telegram_miniapp_auth` |
| Read receipts | Adapter-level `mark_read_typing` hook | Yes | `telegram_hooks.py` provider hooks |

## 2. Setup

### 2.1 BotFather

1. In Telegram, open `@BotFather` and run `/newbot`. Save the token; it is the value of the `token` credential.
   It appears as `<BOT_TOKEN>` in this document. Do not paste it into chat.
2. Choose which modes to enable. The bot only receives update types it is subscribed to (section 2.4).
   - **Bot-to-Bot Communication Mode**: needed only if other bots must reach this bot. Off by default. When on,
     the loop guard (section 6) is the only protection, so keep it on.
   - **Business Mode** (Business settings in BotFather): needed for Secretary features. Without it no
     `business_*` updates arrive. The Secretary policy still decides what the bot does (section 14).
   - **Guest mode**: needed for `guest_message` updates. Without it, guest updates never arrive.
   - **Inline mode** (`/setinline`): needed for `@bot` inline queries.
   - **Inline feedback** (`/setinlinefeedback`, choose Enabled / 100%): needed for the inline answer to arrive by
     itself. Without it Telegram never sends `chosen_inline_result`; the placeholder button then reads
     "Tap to get the answer" and the user presses it to get the reply (see below). After enabling it, tick
     **Inline feedback is on in BotFather** in Settings (or just use inline once: the first received
     `chosen_inline_result` is remembered and clears the Overview "Inline feedback" warning).
3. **Group privacy** (`/setprivacy`): with privacy ON (default) Telegram delivers to the bot only
   `/commands`, replies to the bot's own messages and, when the bot is a group admin, all messages. Plain
   `@mentions` of the bot are NOT delivered while privacy is on and the bot is not an admin. When you rely on
   `mention_required`, turn Privacy OFF in BotFather (`/setprivacy` -> Disable, then remove and re-add the bot
   so it applies) or make the bot a group admin. The gateway then admits only messages addressed to THIS bot:
   its `@username`, a text mention of it, `/cmd@this_bot`, or a reply to one of its messages (mentions of other
   bots do not count). Promoting a group to a supergroup changes its chat id; the approved Room entry is
   re-keyed automatically when the migration service message arrives.
4. **Commands** (`/setcommands`): optional. The gateway publishes commands through `setMyCommands` via
   `telegram_commands.set_commands` (scopes `default`, `all_private_chats`, `all_group_chats`, and others;
   max 100 commands, names `a-z 0-9 _` up to 32 characters, descriptions 1 to 256 characters).
5. **Mini App and menu button**: the cockpit Mini App (section 13.1) is opened from a `web_app` menu button.
   The gateway can set it through the **Commands & profile** tab (`menu_button_payload`, type `web_app`, with
   the Mini App URL `https://<host>/huf/tg-app`). The exact BotFather screens for a Mini App are Telegram's
   and are not described in this repository; the URL must be HTTPS and reachable by Telegram clients.

### 2.2 Integration Settings credentials

Store credentials in the gateway's integration settings, never in the Gateway record text.

| Key | Required | Purpose | Source |
|---|---|---|---|
| `token` | Yes | BotFather token; used for all Bot API calls | `telegram.py` credential schema |
| `webhook_secret` | Yes | Sent as Telegram's `secret_token`; checked against the `X-Telegram-Bot-Api-Secret-Token` header | `telegram.py` (`WEBHOOK_SECRET_HEADER`) |

The cockpit reads `token` from the same integration settings (`telegram_admin.py`). Rotate `webhook_secret` by
changing it in settings and calling `set_webhook` again (section 2.4).

### 2.3 Create the Gateway

1. Create a Gateway with provider **Telegram** and link the integration settings that hold the credentials above.
2. **Direct-message policy** (`direct_policy`): choices are Disabled, Pairing, Allow list and Open. The field
   default is **Allow list**; set **Pairing** for a bot that talks to strangers (see section 3). `Open` admits
   anyone and should be used only for guest-style bots.
3. **Execution user** (`execution_user`): the Frappe user that agent runs execute as. It must hold the
   **Huf Gateway User** role (or a role listed in the `huf_gateway_execution_roles` hook).
   `gateway.py` (`_validate_execution_user_role`) rejects the save otherwise with
   `execution_user '<user>' must have one of these roles: Huf Gateway User`. Do not use Administrator
   (operator guidance; the role check alone does not block it).
4. Set **Room policy**, **Room sender policy** and **Require mention in rooms** (default on) for group use.
5. Optional: Telegram fields in section 11 (voice replies, typing indicator, business policy, join policy,
   admin permissions, default and welcome templates) and pairing TTL (`pairing_ttl_minutes`, default 60).
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

The **Connection** tab (section 12) runs the same steps: token check, webhook card and health.

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

- Unknown direct senders under the **Pairing** policy get a pairing request (`pairing_ttl_minutes`). The
  triggering message never runs the agent. An approved Gateway Access Entry is needed before messages run.
  A pairing code reply is sent only when `pairing_reply_enabled` is on (default off).
- The **Access** tab (section 12) lists pending and approved entries and approves or revokes them.
- Groups: `chat_join_request` updates go to the join policy (section 15). Pairing in a direct chat never
  grants room access.
- Room senders follow `room_sender_policy` (Allow list or Open).
- Consent (STOP/START) is not implemented for Telegram. `consent_required()` in `telegram_hooks.py` returns no
  consent handling. The WhatsApp opt-out path is WhatsApp only (`whatsapp-runbook.md` section 6).
- Bot senders are not admitted by default; section 6 describes the allowlist.

## 4. Agent reply blocks

The agent's reply is parsed for three fenced blocks. Each block is removed from the visible text. The prompt
text for all three is assembled in `telegram_agent_context.py` (`AGENT_INSTRUCTIONS` from the buttons and media
modules), so the agent sees the current format.

### 4.1 Buttons: ```telegram-buttons

Source: `huf/ai/gateway_adapters/telegram_buttons.py` (docstring and `AGENT_INSTRUCTIONS`).

````
```telegram-buttons
{"rows": [[{"text": "Yes", "callback": "yes"}, {"text": "Site", "url": "https://..."}]], "edit": false, "once": true}
```
````

- Top-level keys: exactly one of `rows` (inline keyboard), `reply_keyboard` or `remove_keyboard: true`.
  `edit: true` makes the agent's answer to a press edit the original message. `once: true` removes the
  keyboard on the first press.
- Button kinds (exactly one per button besides `text`): `callback` (id at most 46 bytes), `url`, `web_app`
  (https), `switch_inline` (`"current_chat": true` for the same chat), `copy_text` (at most 256 chars),
  `login_url` (https).
- `reply_keyboard`: `{"rows": [["A", "B"]], "one_time": bool, "resize": bool, "placeholder": str}`; a cell may
  be `{"text", "request_contact"|"request_location"}`.
- Limits: 8 buttons per row, 10 rows, 40 buttons, button text at most 64 characters. Invalid buttons are
  dropped; the block is always stripped. The keyboard goes on the last message part.
- Callback data is HMAC-signed and bound to the chat. A press reaches the agent as `[button: <text>]`.

### 4.2 Media: ```telegram-media

Source: `huf/ai/gateway_adapters/telegram_media_reply.py` (docstring and `AGENT_INSTRUCTIONS`). Media is sent
before the text. A media failure never loses the text; a short note is appended instead.

````
```telegram-media
{"items": [{"type": "photo", "source": "file_url", "value": "/private/files/a.png",
            "caption": "Chart", "has_spoiler": false},
           {"type": "location", "source": "text", "latitude": 52.5, "longitude": 13.4}]}
```
````

- File types: `photo`, `video`, `animation`, `audio`, `voice`, `document`, `sticker`, `video_note`.
- Text-source types: `location`, `contact`, `venue`, `poll`, `dice`. Their fields sit at item level or in `value`.
- Sources: `file_url` (a Frappe File, permission-checked as the gateway execution user), `file_id` (a Telegram
  file id), `url` (public http(s), SSRF-guarded), `text` (for the text-source types only).
- Limits: 10 items per reply; captions 1024 characters; upload 50 MB, photos 10 MB. Two to ten consecutive
  photo or video items (or audio-only or document-only runs) go out as one album (`sendMediaGroup`).
- Sticker and video note items take no caption.

### 4.3 Inbound rich descriptions

Inbound messages are turned into agent-readable text by `telegram_inbound.py`. Each non-text kind has a short
bracketed description, so the agent knows what arrived:

- Stickers: `[sticker]` or `[animated sticker]`-style flavour text plus the emoji.
- GIFs and animations: `[gif/animation <n>s]`.
- Video notes: round-video description with duration.
- Voice notes, audio and video: stored as media and transcribed (section 1).
- Polls: `[poll] <question>: <options>` (options capped at 600 characters in total).
- Dice: `[dice] <emoji> <value>`.
- Venues: `[venue] <title>, <address> (<lat>,<lon>)`.
- Forwarded messages: `[forwarded from <name>]`, from `forward_origin` or the older `forward_*` fields.
- Replies and quotes: the replied-to message (or the quoted text, at most 200 characters) is added as context.

## 5. Admin cockpit

Full design, threat model and command table: `docs/gateways/telegram-admin-cockpit.md`. Operator summary:

1. A signed-in Frappe user calls `create_binding_code(gateway, role_scope)` (POST, whitelisted). It returns
   `<BIND-CODE>` in the form `BIND-XXXXXXXXXX`. Guest and Administrator cannot bind.
2. In a private chat with the bot, `/start <BIND-CODE>` (or the deep link) creates a
   `Telegram Admin Binding`. The code is single use, expires in 10 minutes and is stored hashed.
3. Commands (private chats only): `/me`, `/find`, `/open`, `/approvals`, `/digest`, `/audit` (Admin scope),
   `/help`, `/unbind` (confirmed). Scopes are Viewer, Operator and Admin.
4. Writes follow confirm and audit: button press, then a confirm message with a 5 minute nonce, then the
   action runs as the bound user with `apply_workflow`, and a `Telegram Admin Audit` row is written.
5. The daily digest is wired: `send_daily_digests` is in the daily scheduler in `huf/hooks.py`.
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
- **Opt-out**: there is no STOP/START handling for Telegram (section 3).
- **Bot-to-bot loop guard** (`telegram_loop_guard.py`): bot messages are dropped unless the sender's numeric bot id is
  in the Gateway field `telegram_bot_allowlist` (ids, not usernames, because usernames can change). An allowed bot
  is cut off after `telegram_bot_max_hops` consecutive bot messages in a chat or thread (a human message resets
  it; default 3, 1 to 20), and above `telegram_bot_rate_cap` messages per minute per chat and bot (default 5,
  1 to 1000). Our own bot id is never admitted. State lives in the Frappe cache, so counts are approximate. All
  three values come from the Gateway; no Integration Settings or site config key overrides them.
- **Logs and errors**: `TelegramBotClient.redact` removes the token and its secret half from error text and
  logs (`redact_token` in `telegram_client.py`). Do not add logging that echoes request URLs, which contain the
  token.
- **Voice replies**: need ffmpeg with libopus on every worker host (`ffmpeg -encoders | grep libopus`). Replies
  over 1500 characters are text only (`MAX_TTS_CHARS` in `whatsapp_voice_reply.py`).

## 7. Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| Webhook POST returns **401** `Provider verification failed` | `X-Telegram-Bot-Api-Secret-Token` does not match the `webhook_secret` credential | Set the webhook again with the current `secret_token`, or correct the credential. Failed checks set `last_signature_failure_at`. |
| Webhook POST returns **403** `Gateway is disabled` | Gateway `is_enabled` is off | Enable the gateway. |
| Webhook POST returns **413** | Body larger than the webhook limit | Check for unusual payloads; not expected for Telegram. |
| No updates arrive, webhook shows no error | Webhook URL points elsewhere (tunnel rotated) or another webhook replaced it | Call `getWebhookInfo`, then `setWebhook` with the current URL. |
| Updates arrive but guest or business messages do not | `allowed_updates` was set with a short list | Re-set the webhook with `ALLOWED_UPDATES`. Health check `allowed_updates_ok` shows the gap. |
| Pairing request pending, nothing happens after approval | Pairing creates a pending request; the triggering message never runs | Send a new message after approval. |
| No pairing code reply | `pairing_reply_enabled` is off, or the policy is not Pairing | Check the gateway policy fields. |
| Group message ignored | Bot not mentioned, not replied to, or group privacy blocks it | Mention `@<bot>` or reply to the bot; with Group Privacy ON mentions are not delivered, so disable privacy or make the bot admin. |
| Inline answer never replaces "Thinking..." | BotFather inline feedback is off, so no `chosen_inline_result` | Press the "Tap to get the answer" button, or send `/setinlinefeedback` to BotFather and choose Enabled. |
| Inline results do not show | Inline mode off in BotFather, or the resolver returns nothing | Enable inline mode in BotFather; check the registered resolver. |
| Save fails: `execution_user ... must have one of these roles: Huf Gateway User` | Run-as user lacks the role | Give the user the Huf Gateway User role, or pick another user. |
| Business reply never sent | Policy is Observe (default), or Draft/Reply downgraded (no `can_reply`, guard blocked) | Expected unless the policy and connection rights are set (section 14). |
| Business draft never reaches the owner | Owner chat not known, or the agent run failed | Check the Gateway's default agent and the `Telegram Admin Audit` / error log. |
| Streaming not used | `telegram_streaming` is off on the Gateway, or the chat is a group | Expected (off by default; private chats only). Turn on **Stream replies** in the Settings tab (section 16). |
| Voice reply sent as text | ffmpeg or libopus missing, reply over 1500 characters, or TTS model missing or on a provider without speech | Install ffmpeg with libopus on the worker host; set the agent's `tts_model` (section 16). |
| Admin action refused `bot_not_admin` or `... lacks the 'can_...' right` | The bot is not an admin of the group, or lacks the right | Promote the bot in Telegram with the named right. |
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

## 9. Agent tools

### 9.1 `telegram` (send, read and chat actions)

Registry entry: `TELEGRAM_TOOLS` in `huf/ai/tools/_registry.py`. Dispatch table: `handle_action` in
`huf/ai/tools/telegram.py`. The module docstring lists only an older subset; the dispatch table is authoritative.

Actions (dispatch order as in the table):

- **Send**: `send_message`, `reply_to_message`, `send_photo`, `send_document`, `send_voice`, `send_speech`, `send_audio`,
  `send_video`, `send_animation`, `send_sticker`, `send_media_group` (2 to 10 items), `send_location`,
  `send_contact`, `send_video_note`, `send_venue`, `send_dice`, `send_poll`, `stop_poll`, `send_checklist`
  (Business account; needs the gateway's business flag), `send_template`.
- **Speech** (`send_speech`): `text` (required, max 2000 characters), optional `voice` (TTS voice name; default is
  the agent's `tts_voice`), `caption`, `reply_to_message_id`, `chat_id` (defaults to the current chat). It reuses the
  voice-reply TTS path (agent `tts_model`, Ogg/Opus requested directly, ffmpeg only if needed) and sends via
  `sendVoice`. Recipient scope, per-run/day caps, `delivered_reply` and duplicate-reply suppression apply like any
  send. With no TTS model/provider or on ffmpeg/TTS failure it returns an error text so the agent can send text.
  Gap: image generation is provider-specific and is not part of the telegram tool. The `telegram-media` block has
  no speech item (it would need a format change); use the tool action.
- **Templates**: `list_templates`, `preview_template` (no send), `send_template` (section 10).
- **Chat-state changes are not in the plain tool** (W18-GATE): `pin_message`, `unpin_message` and the forum-topic
  actions (`create/edit/close/reopen/delete_forum_topic`) are removed from the schema and refuse with `owner_required`
  if called. Pin/unpin go through `telegram_admin` (`pin`/`unpin`: owner-run in a paired Admin+ cockpit chat plus a
  human Approve press, even for the bot's own messages). Forum topics have no agent tool; a chat admin does them.
  `delete_message` and `edit_message_text` only act on the bot's own recorded messages inside a gateway run.
- **Chat members**: `get_chat_member`, `get_chat_administrators`, `get_chat_member_count`, `get_chat_info`.
- **Files and history**: `get_file` (saves to a private Frappe File, max 20 MB, returns `file_url`),
  `list_messages` (up to 50 recent logged messages), `get_account_info` (bot identity, modes, webhook health), `get_me`.
- **Message control**: `set_reaction`, `send_chat_action`, `edit_message_text`, `edit_message_caption`,
  `edit_message_reply_markup`, `delete_message` (own messages), `forward_message`,
  `copy_message`, `answer_callback_query`.
- **Gateway-blocked** (refused inside a gateway conversation): `get_updates`, `set_webhook`, `delete_webhook`.
  Use the Connection tab or the management functions instead.

Common rules:

- Inside a gateway conversation `chat_id` defaults to the current chat. Any other chat is checked against the
  gateway's recipient scope (`agent_recipient_scope`, `agent_recipient_allowlist`). Send actions count against
  `agent_send_cap_per_run` and `agent_send_cap_per_day`.
- Send actions also accept `disable_notification`, `protect_content`, `message_effect_id` and `idempotency_key`
  (a repeated key in the same run and chat returns the first result; 24 h cache).
- Media sources: Telegram `file_id`, public https URL, or a Frappe File name or `file_url` (max 50 MB; photos 10 MB).
- `reply_markup` is a JSON object with one of: `inline_keyboard`, `keyboard`, `remove_keyboard`, `force_reply`.
- Outside a gateway, the tool uses explicit `chat_id` values or Integration Settings recipients.

### 9.2 `telegram_admin` (gated)

Registry entry: `TELEGRAM_ADMIN_TOOLS`. Code: `huf/ai/tools/telegram_admin_tools.py`. Everything is OFF by default.

Flags, read from the run's own Gateway (never from arguments):

| Gateway field | Enables |
|---|---|
| `telegram_agent_allow_group_admin` | Group actions |
| `telegram_agent_allow_profile` | Bot profile actions |
| `telegram_agent_allow_business` | Business account actions |

A run outside an enabled Telegram gateway is always refused (`action_not_permitted`).

Actions:

- **Group** (`telegram_agent_allow_group_admin`): `ban`, `unban`, `restrict`, `unrestrict`, `promote`,
  `demote`, `set_chat_title`, `set_chat_description`, `pin`, `unpin`, `delete_message`, `approve_join_request`,
  `decline_join_request`, `create_invite_link`, `revoke_invite_link`, `get_admins`.
- **Profile** (`telegram_agent_allow_profile`): `set_my_commands`, `set_my_name`, `set_my_description`,
  `set_my_short_description`, `set_chat_menu_button`.
- **Business** (`telegram_agent_allow_business`): `get_business_connection`, `send_business_message`,
  `read_business_message`, `delete_business_messages`.

Arguments (one declaration, `huf/ai/tools/telegram_admin_spec.py`): each action lists the argument names it reads and
which are required (`ACTION_ARGS`); the registry parameter list, the tool description, the validation and the approval
card are all generated from that table, so they cannot drift. Validation runs first, before any gate, cap or approval
request, so a bad call never reaches a human and nothing is sent to the Bot API. Unknown argument names are refused
with `invalid_argument`, naming the valid arguments (for example `unknown argument 'text' for set_my_short_description;
use 'short_description'`); a missing required argument and a value of the wrong type are refused the same way. For
`set_my_name`, `set_my_description`, `set_my_short_description` and `set_chat_description` the value must be present:
an explicit empty string is the only way to clear, a missing key never clears. To add an action, add it to `ACTIONS`
and to `ACTION_ARGS` (and `ARG_TYPES` for a new argument); `test_telegram_admin_args` fails if the dispatcher reads an
argument the table does not declare.

The approval card states the action in words with the real values (`Set the bot short description to "Huf test bot"`,
`Ban user 5 for 10 minutes`), then `Action: <name> | chat <id> | bot-wide`; user, chat and message ids always show.

Safety layers, in order:

0. Argument validation (above).
1. Scope: the target chat must be in the gateway's send scope.
2. Bot rights: `getChatMember(bot)` must show the admin right the action needs (for example
   `can_restrict_members` for ban and restrict, `can_promote_members` for promote, `can_delete_messages`,
   `can_pin_messages`, `can_invite_users`, `can_change_info`).
3. Target protection: paired cockpit admins of the gateway are never ban, restrict, promote or demote targets.
   Chat owners and chat administrators are refused for ban, restrict and promote; `demote` may target a plain
   chat administrator (the approving human sees the exact action). Nobody can be given `can_promote_members`.
4. Owner run and human approval for EVERY state change (everything except the read-only `get_admins` and
   `get_business_connection`): the run must come from the private chat of a paired cockpit binding with role Admin
   or higher. Any other run (a group member, forwarded or pasted content, a Viewer/Operator chat) is refused with
   `owner_required` and the agent is told to ask a bound admin. For an owner run the call returns
   `pending_human_approval` and sends signed Approve / Reject buttons to the active Admin bindings; the action runs
   only when an admin presses Approve (single-use nonce, valid 5 minutes, bound to the arguments). There is no
   `confirm` argument: `confirm` and `confirmation_token` are refused as unknown arguments and never count as approval. Bot-wide profile
   actions (`set_my_*`, `set_chat_menu_button`) follow the same rule, so they are only reachable from an owner run.
   With no active Admin binding to ask, the call is refused with `no_admin_available` and nothing is done.
5. Cap: counted actions are capped per run (atomic counter). The limit is the gateway's `agent_send_cap_per_run`
   field; when that field is 0 the code uses 5 (`DEFAULT_CAP`).
6. Audit: every executed or refused action (including `owner_required` and `no_admin_available` refusals) and
   every request for approval writes a `Telegram Admin Audit` row (`agent:<action>`).

Secretary (Telegram Business) Reply and Draft runs process untrusted customer text. They run with NO tools at all
(empty tool allow-list), and the customer's display name is placed inside the quoted untrusted block of the prompt.

## 10. Message templates

Telegram has no native templates. A template is a saved message: text, variables, optional media and buttons.
Module: `huf/ai/telegram_templates.py`. Doctype: `Telegram Message Template`
(`huf/huf/doctype/telegram_message_template/`).

Fields:

| Field | Meaning |
|---|---|
| `template_name` | Required name. Agents and the API refer to templates by this name. |
| `gateway` | Optional Gateway link. Empty means global. A template bound to one gateway refuses other gateways. |
| `is_active` | Inactive templates cannot be sent or listed. Default on. |
| `language`, `description` | Free text for the author. |
| `parse_mode` (Text formatting) | Plain, HTML (default) or MarkdownV2. |
| `body` (Message text) | The text. `{{variable}}` placeholders. |
| `variables` (child `Telegram Template Variable`) | `variable`, `default_value`, `example`. Defaults fill placeholders when the caller omits them. |
| `media_type` | none (default), photo, video, animation, document, audio, voice or sticker. |
| `media` | Attach a Frappe File. Private files are read only if the current session user can read them. |
| `buttons_json` | Buttons in the same schema as the `telegram-buttons` block (section 4.1). |
| `last_used_at` | Set on each successful send. |

Rendering rules:

- `{{name}}` is replaced by the caller's variables, then by the template's variable defaults. Unknown variables
  are reported in `missing` and replaced by an empty string. They raise an error only in strict mode.
- Substituted values are escaped for the template's parse mode (HTML or MarkdownV2), so a value such as `<b>`
  cannot inject markup. Variables inside `buttons_json` are substituted JSON-safely.
- Errors that block sending: text over the Telegram limit, a button problem, media type not supported, or an
  empty result with no media.
- Sending: a media template sends the media with the text as caption when the text fits the caption limit
  (sticker and video note take no caption); otherwise media first and text after. Buttons ride on the last
  message. The gateway's silent and protect-content settings apply. `send_template` refuses when variables are
  missing unless `allow_missing` is set.
- The template layer does not check who may message a chat. Callers (agent tool, UI) must already have passed
  the recipient-scope checks.

Agent actions (section 9.1):

- `list_templates`: active templates usable on the run's gateway.
- `preview_template` (`template_name`, `variables`): renders without sending and returns text, parse mode,
  media, buttons and `missing`/`errors`.
- `send_template` (`template_name`, `variables`): renders and sends. Counts against send caps.

UI: the **Templates** tab (section 12) lists templates and edits them (`TemplateEditor`, `VariablesTable`,
`ButtonsEditor`), previews them (`TemplatePreview`) and sends a test (`SendTestDialog`). Endpoints in
`huf/ai/telegram_management_templates.py`: `list_templates`, `get_template`, `save_template`,
`delete_template`, `preview_template`, `send_test_template`. Reads and writes need the template DocType
permission and the integration manage right (`_require_manager`). A test send is allowed only to a chat that
`is_allowed_test_chat` accepts for the signed-in user.

The Gateway field `telegram_welcome_template` links to a template. The welcome
template is used for welcome messages (`telegram_guard.py`). There is no default-template field: a send names
its template.

## 11. Gateway Telegram fields

Telegram fields on the Gateway doctype (`huf/huf/doctype/gateway/gateway.json`, shown only when provider is
Telegram, except where noted). The Settings tab (section 12) edits the same fields.

| Field | Meaning | Default |
|---|---|---|
| `direct_policy` | Direct messages: Disabled, Pairing, Allow list, Open | Allow list |
| `pairing_ttl_minutes` | Pairing request expiry | 60 |
| `pairing_reply_enabled` | Send a pairing code reply | off |
| `pairing_pending_limit` | Max pending pairing requests | 50 |
| `pairing_reply_daily_limit` | Max pairing replies per day | 20 |
| `room_policy` | Groups: Disabled, Allow list, Open | Allow list |
| `room_sender_policy` | Group senders: Allow list, Open | Allow list |
| `mention_required` | Groups need a mention, reply or command | on |
| `execution_user` | Run-as user (needs Huf Gateway User) | none |
| `default_agent` | Agent for default routing and for business and join decisions | none |
| `telegram_parse_mode` | Text formatting: Plain, HTML, MarkdownV2 | HTML |
| `telegram_silent_replies` | Send replies without notification | off |
| `telegram_protect_content` | Protect content (no forwarding or saving) | off |
| `preview_url` | Link previews: Default (off), On, Off. Only On shows previews | Default (off) |
| `voice_reply_mode` | Voice notes: Off, Voice only, Text and voice | Off |
| `typing_indicator` | Send typing action while the agent works | on |
| `telegram_streaming` | Live reply streaming in private chats; the only switch (section 16) | off |
| `telegram_inline_enabled` | Inline mode switch. **Not read at runtime** (section 17) | on |
| `telegram_business_policy` | Business chats: Ignore, Observe, Draft, Reply | Observe |
| `telegram_join_policy` | Group join requests: Queue, Decline, Agent | Queue |
| `telegram_agent_allow_group_admin` | Agent may use group admin actions | off |
| `telegram_agent_allow_profile` | Agent may edit the bot profile | off |
| `telegram_agent_allow_business` | Agent may use the Business account | off |
| `telegram_bot_allowlist` | Allowed bot ids (numeric only, comma or line separated); read by the loop guard | empty |
| `telegram_bot_max_hops` | Consecutive bot messages allowed before cut-off, 1 to 20 | 3 |
| `telegram_bot_rate_cap` | Messages accepted per minute from one allowed bot in one chat, 1 to 1000 | 5 |
| `telegram_welcome_template` | Welcome template for new group members | none |
| `agent_recipient_scope` | Who agents may message: Current contact, Allow-list, Approved contacts, Any number | Current contact |
| `agent_recipient_allowlist` | Chat ids or @usernames for Allow-list scope | empty |
| `agent_send_cap_per_run` | Agent sends per run (also the admin action cap, section 9.2) | 20 |
| `agent_send_cap_per_day` | Agent sends per day | 200 |
| `default_agent` | see above | none |
| `integration_settings` | Credentials source (section 2.2) | none |

## 12. Management UI

Page: `/telegram` (`frontend/src/pages/TelegramManagePage.tsx`). Requires the `system.integrations.manage`
capability (`ProtectedRoute` in `frontend/src/App.tsx`). A gateway is picked with `?gateway=`, and the tab with
`?tab=`. Tab registry: `frontend/src/components/telegram/tabs.ts`. No tab currently sets a `permission`, so
every tab shows to anyone who can open the page. Server-side checks still apply to each call.

| Tab (`?tab=`) | What it does | Server checks |
|---|---|---|
| Overview (`overview`) | Health, setup checklist, counts for the gateway | `get_telegram_overview`, `get_telegram_health` (gateway admin) |
| Settings (`settings`) | Edits the Telegram gateway fields (section 11), grouped as replies, access, modes and agent permissions | Gateway write (`_require_gateway_admin`) |
| Templates (`templates`) | List, edit, preview and test-send message templates (section 10) | Template DocType permission and the integration manage right |
| Messages (`messages`) | Recent messages with a detail sheet | Gateway admin (`_require_admin`) |
| Access (`access`) | Pairing requests and access entries: approve or revoke | Gateway admin |
| Send (`send`) | Send a message from the gateway to a chat | Server-side checks in the management API |
| Admin bindings (`bindings`) | Cockpit bindings: create a binding code, revoke bindings | Gateway admin |
| Commands & profile (`commands`) | Bot commands, profile name and description, menu button (including the Mini App `web_app` button) | Gateway admin; profile actions go to Telegram |
| Connection (`connection`) | Token check, webhook card, webhook set and delete | Gateway admin; `set_webhook` needs the secret |

The **audit** read is restricted to System Manager and Huf Manager (`telegram_admin.py`). Gateway admin means
`System Manager` or `Huf Admin` (or the integration manage capability), or write permission on the Gateway.

## 13. Mini App and Guard

### 13.1 Admin Mini App (`/huf/tg-app`)

- Frontend route: `frontend/src/App.tsx` (`tg-app`, under the `/huf` basename), page `TelegramAppPage`. Opened from
  the bot's menu button or a button in the cockpit. It only works inside Telegram.
- Auth: the page POSTs `Telegram.WebApp.initData` to
  `/api/method/huf.ai.telegram_admin.telegram_miniapp_auth` (`init_data`, `gateway`). The response carries a
  15 minute bearer token. Every later call sends it in `X-Huf-Tg-Token`. Endpoints and the response format are
  in `docs/gateways/telegram-miniapp-api.md`.
- Setup steps:
  1. Serve the frontend at `https://<host>/huf/tg-app` over HTTPS.
  2. Create a Telegram Admin Binding first (section 5); the Mini App only works for a bound user.
  3. Point the bot's Mini App or menu button at that URL. Either use BotFather (Telegram's screens) or the
     **Commands & profile** tab (`menu_button_payload`, type `web_app`).
  4. Open the bot in Telegram, tap the menu button, and check the Overview of the Mini App.

### 13.2 Guard page (`/tg_guard`)

- Served by `huf/www/tg_guard.py`. Static shell; the question and the answer check run in `huf/ai/telegram_guard.py`.
- It is used when the join policy is in use, a join request carries a `query_id`, and captcha is enabled. Enable it
  with the Gateway field `telegram_guard_captcha` (Off, Arithmetic or Emoji). Off means off: no site config key
  overrides it.
- The bot sends the page with `sendChatJoinRequestWebApp`. The URL is `https://<host>/tg_guard?g=<gateway>&n=<nonce>`.
- Each challenge is single use, expires after 600 s, and allows 3 attempts. Success approves the request, wrong
  answers decline it. Both guest endpoints are authenticated only by the initData HMAC and are rate limited.
- Setup steps:
  1. Serve the site on HTTPS (Telegram Web Apps require it).
  2. Make the bot an admin of the group with `can_invite_users` (needed to approve or decline requests).
  3. Set `telegram_join_policy` to Agent or Queue (section 15), and set `telegram_guard_captcha` on the Gateway.

## 14. Secretary (business) mode

Source: `telegram_business.py` (policy engine and drafts), `telegram_business_agent.py` (agent policy and draft
producer, registered by `telegram_business_agent_hooks.py`).

Policy: `Gateway.telegram_business_policy`, read per message.

- **Ignore**: nothing is recorded or answered.
- **Observe** (default): messages are recorded, never answered. Edits and deletions are recorded only.
- **Draft**: the target agent writes a proposed reply. It is delivered to the owner's private chat with
  **Approve**, **Edit** and **Reject** buttons. Nothing reaches the customer until the owner approves.
  Drafts are stored in the cache for 24 hours (`DRAFT_TTL` in `telegram_business.py`).
- **Reply**: the same agent run is sent straight to the customer as the owner. It needs `can_reply` on the
  connection, a per-chat rate limit, and every registered reply guard (quiet hours, owner online) to pass.
  Otherwise it falls back to Draft. An optional `business_disclosure` credential is appended as a footer.

Downgrades: Draft and Reply fall back to Observe when the connection is disabled or lacks the right, and Draft
falls back when no draft producer is registered. The producer is registered in code, so it is present.

Owner approval flow: the callback `bz:<a|e|r>:<draft_id>` is signed and must come from the owner's chat.
Approve sends the draft as the owner. Edit puts the draft in an editing state and prompts for the new text.
Reject finishes the draft. Expired or used drafts show a stale message.

Gateway validation: Draft and Reply need a default agent (`gateway.py`). Own messages, bot-sent messages and bot
senders never trigger a policy.

Agent admin actions for business (`telegram_agent_allow_business`, section 9.2) are separate from the policy.

## 15. Join policy (group join requests)

Gateway field `telegram_join_policy`, default **Queue**. Source: `huf/ai/telegram_guard.py`.

- **Queue**: leave the request to human admins. The bot never auto-approves.
- **Decline**: decline the request.
- **Agent**: queue the request at once (inside Telegram's 10 second window), then a background job asks the
  gateway's default agent for a strict JSON decision `{"decision": "approve|decline|queue", "reason": ""}`.
  Parse failure, an invalid value or a timeout leave the request queued. Approve and decline use
  `approveChatJoinRequest` and `declineChatJoinRequest`. The Bot API does not document whether these work after a
  queue answer; failures are logged and the entry stays pending.
- Welcome messages use `telegram_welcome_template` with a cooldown. Every approve or decline is logged and
  written to `Telegram Admin Audit` when that doctype exists.
- Guard captcha (section 13.2) is an extra step when enabled and a `query_id` is present.

Agent policy requires `default_agent` (`gateway.py`).

## 16. Streaming and voice replies

### 16.1 Streaming

- The only switch is the Gateway checkbox **`telegram_streaming`** (`telegram_stream.streaming_enabled`). It is off
  by default and applies only to private chats. There is no site config override.
- Streaming uses `sendMessageDraft` to animate a reply draft. A reply's updates share one draft id.

### 16.2 Voice replies

- Gateway field `voice_reply_mode`: Off (default), Voice only, or Text and voice. Replies over 1500 characters are text only.
- Speech is generated by the agent's **TTS model** (`Agent.tts_model`, an AI Model link), with its voice from
  `Agent.tts_voice`. The API key comes from that model's own AI Provider (`huf/ai/handlers/media.py`
  `_resolve_tts_config`). The default TTS model per provider is in `_get_default_tts_model`; the code has entries for
  OpenAI, Azure, Google/Gemini, Vertex AI, ElevenLabs, AWS and MiniMax. **Anthropic has no TTS entry**, so an
  Anthropic-only agent produces no voice reply and falls back to text.
- Set `Agent.tts_model` to a model on a provider that supports speech (for example an OpenAI TTS model). The same
  rule applies to `stt_model` (transcription of inbound voice) and `image_generation_model`: point them at a
  provider that offers that capability. Anthropic models are for text only in this codebase.
- Audio is converted to Ogg/Opus with ffmpeg (`whatsapp_send_file.to_ogg_opus`). Missing ffmpeg or libopus, a
  failed TTS call or an empty result falls back to the text reply. A reply is never lost.

## 17a. Test environment

Telegram runs a separate test environment (test servers, test accounts, test bots). Turn on **Use Telegram test environment** on the Gateway (Settings, Modes) to point the whole gateway at it.

- Bot API calls go to `https://api.telegram.org/bot<token>/test/<METHOD>` and file downloads to `/file/bot<token>/test/<path>`. This covers sending, getFile downloads, and webhook management (setWebhook, getWebhookInfo, deleteWebhook), the agent tools and the management cockpit. One helper (`bot_api_url` / `bot_file_url` in `telegram_client.py`) builds every URL.
- Use only with a bot token created in the test environment (via @BotFather on a test account). A normal production token does not work there, and a test token does not work on production, so leave the flag off for normal bots.
- Mini App `initData` validation is unchanged (same HMAC algorithm). In the test environment `initData` is signed with the test bot's token, so the Integration Settings token must be the test bot's token.
- Tokens stay redacted in logs and errors; the `/test/` segment is not secret.

## 17. Known gaps

Each item below was checked against the code. "Not wired" means nothing on the runtime path reads it.

1. **Inline "Run" button**: `RUN_CALLBACK_PREFIX = "inl:run"` is defined in `telegram_inline.py`, but no handler
   dispatches it. Pressing it does nothing.
2. **Gateway `telegram_inline_enabled`**: saved, not read by the inline handlers. Inline mode is governed by
   BotFather and the resolver registry.
3. **Consent (STOP/START)**: not implemented for Telegram (section 3).
4. **Inline feedback**: no code path. BotFather setting only (section 2.1).
5. **Admin action cap**: uses `agent_send_cap_per_run` (default 20), not a separate admin cap, and falls back to 5
   only when the field is 0. Intended or not, the cap is shared with sends.

Resolved since older notes: the Secretary draft producer is registered (section 14), and inbound voice notes are
transcribed through the provider-neutral media prep (section 1).

## 18. Live test checklist

Run these against a test bot and a test gateway on a test host. Use the bot's own test chat. Expected results
assume the default settings unless a row says otherwise.

| # | Check | Steps | Expected result |
|---|---|---|---|
| 1 | Pair | Set direct policy to Pairing; message the bot from an unknown account; approve on the Access tab; send again | First message is held (no agent reply). After approval, the next message gets an agent reply. |
| 2 | Text | Send "hello" in the paired private chat | One agent reply, HTML formatting, typing indicator shown first. |
| 3 | Buttons | Ask the agent for a Yes/No keyboard with `telegram-buttons` | Keyboard appears on the last message. Tapping Yes sends `[button: Yes]` to the agent. With `once: true` the keyboard disappears after one tap. |
| 4 | Media block | Ask for a photo from a Frappe File with a `telegram-media` block | Photo arrives before the text. Caption at most 1024 characters. Block not visible in text. |
| 5 | Voice | Set `voice_reply_mode` to Voice only, agent `tts_model` on OpenAI; send a voice note | Reply is a voice note. Without ffmpeg/libopus or with an Anthropic-only agent, a text reply arrives instead. |
| 6 | Template | Create a template with a `{{name}}` variable; ask the agent to `preview_template`, then `send_template` | Preview shows the substituted text. Send delivers it with its buttons. Missing variable blocks the send unless `allow_missing`. |
| 7 | Inline | Type `@<bot> query` in another chat | Article results appear when inline mode is on in BotFather. Tapping "Run" does nothing (known gap 1). |
| 8 | Admin bind | Create a binding code on the Admin bindings tab; send `/start <BIND-CODE>` privately; send `/me` | Binding created; `/me` shows the bound user and scope. The code cannot be reused. |
| 9 | Admin action | Enable `telegram_agent_allow_group_admin`; ask the agent to ban a test user in a test group | Refused without the bot's ban right. With the right: from a group member or non-admin chat the call is refused with `owner_required`; from the paired Admin's private chat it returns `pending_human_approval`, and the ban runs only after the admin presses Approve, with an audit row. Chat admins are never ban targets. |
| 10 | Join request | Join policy Queue: request to join a test group. Then switch to Agent | Queue: request stays pending for admins. Agent: request queued, then approved or declined by the agent decision. With a welcome template set, a joining member gets the welcome (60 s cooldown). |
| 11 | Guard | Set `telegram_guard_captcha` to Arithmetic, join a Guard group | The join request shows the Guard Mini App. A wrong answer three times declines; the right answer approves. |
| 12 | Business draft | Connect the business account with Business mode on; set policy Draft; send a message to the business account from another account | The owner's private chat gets a draft with Approve, Edit, Reject. Approve sends it as the owner. Nothing reaches the customer before approval. |
| 13 | Business Observe | Default policy; message the business account | Message recorded in the Messages tab; no reply sent. |
| 14 | Streaming | Turn on `telegram_streaming`; private chat with a long reply | Reply animates as a draft. With the checkbox off the reply arrives in one piece. |
| 15 | Webhook health | Connection tab, then Check | Webhook URL shown; `allowed_updates_ok` true; pending count 0 after traffic. |

Record the Telegram message ids and Frappe Gateway Event rows for each check. Never record the bot token.

