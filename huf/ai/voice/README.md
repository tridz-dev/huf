# Voice session contract

## Overview

HUF's voice layer is a control plane on top of the `Agent` doctype: it authenticates and
authorizes the caller, brokers a session with the Agent's configured voice engine, and (as of
this change) persists what it reasonably can. It does not provide a call UI itself - a browser
client that opens a WebSocket/microphone and speaks the engine-specific wire protocol is built
separately against this contract.

## Starting a session

`huf.ai.voice.api.start_session(agent, conversation_id=None)` - session-authenticated (whitelisted,
requires `frappe.session.user` to have read access to `agent`). `start_public_session(publishable_key,
agent)` - `allow_guest=True`, for embedded/unauthenticated callers; gated by an HMAC-safe
`publishable_key` match, `embed_enabled`, and an Origin allowlist, never by `frappe.session.user`.
Both funnel into `_mint_session`, which resolves the Agent's `voice_engine`/`voice_config` and
calls `engine.start_session(...)`.

Real response shapes:

- **ElevenLabs** (`elevenlabs_convai`): `{"engine": "elevenlabs_convai", "signed_url": ..., "agent_id":
  ..., "conversation_id": ..., "dynamic_variables": {"huf_conversation_id": ...}}` (the last two keys
  only when a `conversation_id` was supplied). Threading is **client-cooperative**: ElevenLabs has no
  server-side way to receive `conversation_id` at mint time, so the browser client must itself echo
  `{"huf_conversation_id": conversation_id}` back to ElevenLabs as a dynamic_variable in its own
  `conversation_initiation_client_data` when it opens the WebSocket - HUF cannot enforce this.
- **litellm_realtime**: `{"engine": "litellm_realtime", "session_id": ..., "sidecar_ws_path":
  "/voice/realtime/<session_id>", "conversation_id": ...}`. Threading is fully server-side: the engine
  stashes `conversation_id` into `frappe.cache()` under the session id, and the sidecar reads it back
  when the browser connects - no client cooperation required.

## Capabilities

`get_capabilities(engine)` returns `engine_class.capabilities()`. Current shipped values:

- **elevenlabs_convai**: `instructions: False` (the ElevenLabs agent runs its own dashboard-configured
  prompt), `tools: True`, `memory: False`, `persistence: True`, `barge_in: True`.
- **litellm_realtime**: `instructions: False` (the sidecar relays raw provider frames, never sends
  `Agent.instructions`), `tools: True`, `memory: False`, `persistence: True`, `barge_in: True`.

## Ending / mid-session

`end_session(agent, session_id)` delegates to `engine.end_session`: ElevenLabs has no documented REST
endpoint to end a conversation server-side, so it's the base-class no-op (the browser closing the
WebSocket ends the call); litellm_realtime deletes its cache stash so a reconnect can't reuse it.

`send_to_session(agent, session_id, kind, text)` does **not** currently work for either engine. Neither
engine overrides `VoiceEngine.send_to_session`, so it hits the base class's `raise
NotImplementedError`, which the API wrapper turns into a `frappe.ValidationError` ("does not support
sending content into an active session"). This is wired end-to-end but unimplemented in every engine.

## Persistence

- **ElevenLabs**: full transcript + `Agent Run`, but **only** via the post-call webhook (see
  `elevenlabs_convai_api.py`, not read in this pass). A call where the webhook never fires - not
  configured, or ElevenLabs can't reach the site - persists nothing.
- **litellm_realtime**: agent-spoken turns only, best-effort, as plain `Agent Message` records (`kind:
  "Audio"`, via `ConversationManager.add_message`) on a conversation resolved/created by
  `huf.ai.voice.persistence.get_or_create_voice_conversation` (channel `"realtime_voice"`). The sidecar
  parses raw OpenAI Realtime WebSocket frames in `_try_persist_agent_turn`, persisting only
  `response.audio_transcript.done` events; anything else, or a JSON parse failure, is silently
  swallowed by design so persistence never breaks the live audio relay. **User speech turns are not
  persisted** - only agent-spoken text is captured. Persistence resolution itself is best-effort: if
  `get_or_create_voice_conversation` raises, the call still connects with `cm`/`conversation` set to
  `None` and nothing is recorded for that call.

`huf/ai/voice/persistence.py` exists and holds `get_or_create_voice_conversation` and
`record_voice_turn`; it is deliberately separate from the ElevenLabs webhook's own inline
`ConversationManager` usage.

## Conversation-access validation happens once, at `start_session`

`conversation_id` is only ever authorization-checked in one place: `huf.ai.voice.api.start_session`,
via `_check_conversation_access`, while `frappe.session.user` is still the real caller (same agent,
and the user owns the conversation or holds `chat.view_all`). This is deliberate, not an oversight:
everything `conversation_id` is handed to afterward runs in a context that cannot recover the real
caller's identity - the litellm_realtime sidecar connects as Administrator (`frappe.connect()`
defaults `set_admin_as_user=True`), and the ElevenLabs webhook runs as Guest (`allow_guest=True`).
Re-checking ownership downstream in either of those contexts would either always pass (Administrator
holds every capability, including `chat.view_all` - a real cross-user leak was found and fixed here
during review) or always fail for the realistic case (Guest owns nothing - this broke the ElevenLabs
webhook's `Agent Run` audit record entirely on first cut, also fixed here: it now falls back to a
fresh conversation and logs, rather than aborting, if the echoed `huf_conversation_id` doesn't check
out downstream). If a third caller ever wants to thread `conversation_id` through
(`start_public_session` deliberately doesn't - embed callers are anonymous, there's no
authenticated owner to check against), it needs this same check, at that same call site, before the
id is ever handed to `_mint_session`.

## Known gaps

- `send_to_session` is unimplemented on both shipped engines - always raises/throws today.
- Realtime (litellm_realtime) persists agent turns only; user-spoken turns are not captured anywhere.
- ElevenLabs persistence has a single point of failure: a missed/unreachable webhook call persists
  nothing for that entire conversation, with no fallback path.
- ElevenLabs `conversation_id` threading depends on the client actually echoing
  `huf_conversation_id` back to ElevenLabs correctly - HUF cannot enforce that a client does this (or
  does it honestly); a client that gets it wrong or omits it just gets a fresh conversation instead
  of continuity, not an error, and not a security issue (see the section above for why).
- No engine currently reads Agent memory into context (`memory: False` on both).
