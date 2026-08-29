# Huf Playground — Multimodal Roadmap (Plan Stub)

Status: plan seed / RFC. No implementation. Written against the `huf` worktree at
`Tracks/safwan-erooth.PlaygroundMediaRoadmap/worktrees/huf` (branch `main`).

---

## Overview

Huf's Playground (`/playground`, `frontend/src/pages/PlaygroundPage.tsx`) is today a
**text-only prompt bench**: pick an agent *or* a raw provider+model, type a prompt, set
temperature / max tokens, hit Run, compare two columns side by side, keep a local run ledger.

Meanwhile the *agent runtime underneath it already speaks five other modalities*. Image
generation, TTS, STT, OCR/document understanding and full realtime voice all exist as
whitelisted backend handlers, DocType fields and — for voice — a separate ASGI sidecar
process. None of it is reachable from the Playground. A developer wanting to answer
"does `eleven_flash_v2_5` sound better than `eleven_turbo_v2_5` for this line?" or
"does `gpt-image-1-mini` hold up against `gpt-image-1` for this prompt?" has no bench:
they have to build an agent, wire a tool, and go through chat.

The goal of this track is to close that gap — turn the Playground from a text bench into a
**modality bench**, reusing the media plumbing that already exists rather than building a
parallel stack.

The headline finding from the code read: **this is mostly a frontend and thin-API-shim
problem, with exactly one genuinely hard architectural piece (realtime voice transport).**

---

## Current State (What Huf Already Has)

### Playground frontend — the surface we are extending

| File | Role |
| --- | --- |
| `frontend/src/pages/PlaygroundPage.tsx` (216 L) | Page shell; loads agents + providers; owns `mode`, per-slot config state, run ledger |
| `frontend/src/components/playground/PlaygroundShell.tsx` | `WorkSurfaceFrame` wrapper; **tabs are already a first-class concept** — `[{value:'playground',label:'Single'},{value:'compare',label:'Compare'}]` |
| `frontend/src/components/playground/types.ts` | `PlaygroundConfig` (agentName, provider, model, prompt, evaluationCriteria, temperature, maxTokens), `RunOutcome`, `SlotState` |
| `frontend/src/components/playground/ConfigStrip.tsx` | Agent / provider / model / params selector; loads models via `getModels(provider)` |
| `frontend/src/components/playground/runExecutor.ts` | `executeRun(config)` → `runAgentSync` or `runPromptSync`, plus Agent Run telemetry enrichment |
| `frontend/src/components/playground/{PromptPanel,ResponsePanel,TraceRail,RunLedger,ledgerStorage}.tsx/ts` | Input, output, trace rail, localStorage ledger (50 entries) |
| `frontend/src/services/consoleApi.ts` | Only four backend calls, all text: `huf.ai.console_api.{run_prompt_sync, generate_prompt, evaluate_run, save_prompt_template}` |

Architecturally this is a good base: the shell already renders a tab bar, config is a plain
serializable object, and `executeRun` is a single dispatch point. A modality axis slots in
naturally.

### Backend media handlers — already whitelisted, already working

`huf/ai/handlers/media.py` (924 L) exposes four `@frappe.whitelist() async def` handlers:

| Handler | Signature highlights |
| --- | --- |
| `handle_generate_image` | `prompt, size="1024x1024", quality="standard", n=1, agent_name, conversation_id` — LiteLLM `image_generation()`; model from `Agent.image_generation_model` or provider auto-detect (`_get_default_image_model`) |
| `handle_generate_audio` | `input, voice, model, speed=1.0, response_format="mp3", agent_name, conversation_id` — LiteLLM `speech()`; `_resolve_tts_config` / `_get_default_voice` / `_get_default_tts_model` |
| `handle_transcribe_audio` | `file_id, file_url, file_path, language, model, agent_name` — pure tool, delegates to the audio service, deliberately creates **no** Agent Message |
| `handle_ocr_document` | `file_id, file_url, pages, include_images, model, agent_name, conversation_id, create_message=True` — PDFs / images / office docs |

Supporting modules:

- `huf/ai/audio_service.py` (803 L) — canonical STT service: `save_audio_upload`,
  `import_local_audio`, `resolve_local_audio_path` (allow-listed import dirs),
  `resolve_stt_config`, `transcribe_audio_file`, `_call_stt_provider`,
  `create_audio_user_message`.
- `huf/ai/audio_api.py` (132 L) — clean public `transcribe()` endpoint: accepts exactly one of
  `file_id` / `b64data`+`filename` / `file_path` (System Manager only), optional
  `create_message`. **This is already very close to what a transcription playground tab needs.**
- `huf/ai/ocr_engine.py` — strategy selection (`_determine_strategy`: local extractor vs LiteLLM
  OCR endpoint vs vision model), local extractors, file hashing, `_default_model(provider, strategy)`.
- `huf/ai/transcription_handler.py` — `execute_provider_capability`, `handle_speech_to_text`.

### Voice / realtime — a control plane exists, a client does not

`huf/ai/voice/` is a complete, documented session-broker layer (`huf/ai/voice/README.md` is
unusually candid and worth reading before any work here):

- `api.py` — `list_engines`, `get_config_schema`, `get_capabilities`, `list_voices`,
  `start_session(agent, conversation_id)`, `end_session`, `send_to_session`,
  `start_public_session(publishable_key, agent)` (guest, HMAC-safe key + Origin allowlist).
- `engines/elevenlabs.py` (`elevenlabs_convai`) — returns a **signed WebSocket URL**; threading of
  `huf_conversation_id` is client-cooperative (Huf cannot enforce it); persistence via post-call
  webhook only.
- `engines/litellm_realtime.py` — returns `{session_id, sidecar_ws_path: "/voice/realtime/<id>"}`;
  stashes `{agent, model, api_key_provider, conversation_id}` in `frappe.cache()` under
  `huf:voice:realtime:session:{session_id}`, TTL 300 s.
- `sidecar/app.py` — **standalone FastAPI + uvicorn ASGI process**, separate from the gunicorn
  bench workers, because (quoting the module docstring's reasoning) WSGI cannot hold a long-lived
  duplex WebSocket. Run as `FRAPPE_SITE=<site> REALTIME_SIDECAR_PORT=8091 python -m
  huf.ai.voice.sidecar.app`. Optional dependency group `realtime = ["fastapi", "uvicorn[standard]"]`
  in `pyproject.toml`. Proxies raw OpenAI Realtime frames; close codes 4404 / 4500 / 4502.
- `persistence.py` — `get_or_create_voice_conversation` (channel `realtime_voice`), `record_voice_turn`.
- DocType `Voice Engine`: `engine_key`, `label`, `kind` (**`composed` | `realtime`**), `provider`, `enabled`.

Known gaps already documented by the team (do not rediscover these):
`send_to_session` raises `NotImplementedError` on **both** engines; realtime persists **agent turns
only** (user speech is captured nowhere); ElevenLabs persistence has a single point of failure in the
webhook; and `huf/public/js/huf-voice.md` states outright that opening the actual audio connection
"is not yet implemented by this bundle". **There is no live voice UI anywhere in Huf today** —
`frontend/src/components/agent/VoiceTab.tsx` and `components/settings/VoiceSettingsTab.tsx` are
configuration forms, not clients.

### Data model — mostly ready

`Agent Message` (`huf/huf/doctype/agent_message/agent_message.json`) already carries:

- `kind` Select: `Message, Tool Call, Tool Result, Status, Error, **Image, Audio, Video**`
- `generated_image` (Attach Image), `generated_audio` (Attach), **`generated_video` (Attach)**
- `tts_model`, `tts_voice`, `stt_model` (Links to AI Model), `voice_message` (Attach)
- `content_type` Select includes `Image`

Notably `generated_video` and `kind: Video` **already exist** — the "missing video field" the task
brief hypothesized is not missing. There is no generation handler behind it yet, which is the
opposite gap.

`AI Model.modalities` (Data field, comma-joined) options:
`Text, Image, Text-to-Speech, Transcription, Embeddings, Vision, OCR, Speech-to-Speech`.
Seeded in `huf/install.py`: `eleven_multilingual_v2` / `eleven_turbo_v2_5` / `eleven_flash_v2_5`
(TTS), `gpt-image-2` / `gpt-image-1` / `gpt-image-1-mini` / `chatgpt-image-latest` (Image, both
OpenAI and OpenRouter-prefixed), `tts-1` / `tts-1-hd`, `whisper-1`, `gpt-realtime-whisper` (STT).
`Speech-to-Speech` is a valid option that **no seeded model claims** — realtime models are not
modelled as AI Model rows at all today.

`Agent` carries `image_generation_model`, `tts_model`, `tts_voice`, `stt_model`, `enable_ocr`, and a
whole `voice_tab` (`voice_enabled`, `voice_engine`, `voice_config`, `voice_greeting`).
`AI Provider` has **no realtime-capable flag** — realtime capability lives only on `Voice Engine.kind`.

### Frontend media libraries already installed

From `frontend/package.json`:

- `media-chrome@^4.18.0` — themeable `<media-controller>` audio/video player elements. **Already
  there; use it for TTS/audio playback rather than adding a new player.**
- `socket.io-client@^4.7.5` — existing chat streaming transport.
- `ai@^6.0.116` (Vercel AI SDK), `streamdown`, `tokenlens`.
- **Not present:** any waveform library (wavesurfer/peaks), any WebRTC helper, any audio-worklet
  PCM resampler. These are the real net-new frontend dependencies.

Also already built: `frontend/src/components/ai-elements/speech-input.tsx` — a dual-mode mic button
that uses the Web Speech API when available and falls back to `MediaRecorder` +
`navigator.mediaDevices.getUserMedia`, uploading to
`huf.ai.agent_chat.upload_audio_and_transcribe_web`. **Phase 2 should lift capture logic from here,
not reinvent it.**

---

## Reference Patterns (OpenAI / ElevenLabs / Anthropic)

### OpenAI Playground

- **Modality as a top-level mode selector**, not a hidden setting. Chat / Realtime / Assistants /
  TTS / Transcription are distinct surfaces sharing one model+params rail.
- **Realtime tab**: a session-oriented UI, not a request/response one. Press-to-connect →
  persistent session → mic capture with a live input level meter → streaming interleaved transcript
  (user turns and assistant turns as they arrive, not on completion) → barge-in supported →
  explicit End session. Session config (voice, VAD threshold, turn detection mode, instructions) is
  set *before* connect and partially mutable mid-session.
- **Transcription**: file drop zone + language hint + model picker → transcript with optional
  timestamps/segments.
- **Image**: prompt + size + quality + n → grid of results, each downloadable, each carrying its
  generation params so a result can be re-run or forked.
- Everything writes into a shared run history with cost/latency per run.

### ElevenLabs

- **TTS playground**: text box + voice picker (with per-voice preview) + model picker
  (flash/turbo/multilingual, framed as a latency↔quality tradeoff) + stability/similarity sliders →
  generate → inline player with waveform scrub, plus a persistent history of generations.
  The *voice picker is the primary control*, ahead of the model picker — a UX detail Huf's
  agent-centric `ConfigStrip` currently has no slot for.
- **Conversational AI (agent) testing**: an in-dashboard "Test AI agent" widget — click to talk,
  live transcript pane on one side, a latency/turn breakdown on the other, post-call the
  conversation appears in a call history with full transcript and per-turn timing.
- Model comparison is done by re-generating the same text on a different model and A/B-ing the two
  audio clips from history — exactly the shape Huf's existing Compare mode already implements for text.

### Anthropic Console

- Deliberately narrower: a **Workbench** with system prompt / messages / params, plus file and image
  attachment for vision, and an Evaluate tab that runs a prompt across a test-case table.
- Key transferable idea: **attachment as a first-class part of the prompt input**, not a separate
  tab. Vision/document understanding is not its own mode — it is the text mode with a file attached.

### Mapping to Huf

| Pattern | Fit for Huf |
| --- | --- |
| Modality as top-level tab | Direct fit — `PlaygroundShell` already renders `WorkSurfaceTab[]`. Extend `PlaygroundMode` from `'playground' \| 'compare'` to a modality × layout matrix. |
| Request/response modalities (image, TTS, STT, OCR) | Direct fit — plain `frappe.call` POST against the existing `handlers/media.py` endpoints. Same `executeRun` dispatch shape, just a wider `RunOutcome`. |
| Compare-two-columns | Direct fit and arguably *more* valuable for media than for text (two TTS voices, two image models side by side). Reuse `CompareView` with a modality-specific result renderer. |
| Run ledger / history | Direct fit, with one caveat: `ledgerStorage.ts` is `localStorage`, capped at 50 entries. Audio/image results cannot be stored inline — the ledger must hold **file URLs**, and generated files need a retention story. |
| Realtime session UI | **No fit with the current transport.** See Risks. Needs the sidecar, a browser WS client, and PCM capture — none of which exist. |
| Attachment-in-prompt (Anthropic style) | Good fit for OCR/vision: rather than a separate OCR tab, allow a file attachment in the existing text prompt panel that routes through `handle_ocr_document` and prepends the extraction. Consider offering **both** (dedicated tab for isolating the OCR step, attachment for end-to-end). |

---

## Proposed Phases

Ordering principle: **highest ratio of (developer value) to (new architecture) first.** Phases 1–3
are essentially UI on top of endpoints that already work. Phase 4 is where the real engineering is.

### Phase 0 — Foundation (prerequisite for everything below)

Small, unglamorous, and it unblocks all later phases.

**Backend**

1. **Modality-aware model listing.** `ConfigStrip` calls `getModels(provider)` and shows everything.
   Add a modality filter so a TTS tab offers only `Text-to-Speech` models. `AI Model.modalities`
   already holds the data and `providerApi.getModalityOptions()` already reads the Select options
   from the DocType meta — this is a filter parameter, not a schema change.
2. **A console-layer shim per modality.** `handlers/media.py` handlers are *agent tools*: they take
   `agent_name` and (for image/audio/OCR) write Agent Messages into a `conversation_id`. The
   Playground wants **agentless, provider+model-direct, no-persistence** runs, mirroring how
   `console_api.run_prompt_sync` relates to `run_agent_sync`. Add
   `huf.ai.console_api.{run_image_sync, run_tts_sync, run_stt_sync, run_ocr_sync}` that accept an
   explicit provider+model, bypass Agent resolution, skip message creation, and return uniform
   telemetry (`latency_ms`, `cost`, `model`, plus artifact URL). Do **not** re-implement generation —
   these call the same underlying services.
3. **Generated-artifact retention policy.** Playground runs will produce orphan files (images, mp3s)
   attached to no Agent Message. Decide now: private `File` records tagged with a
   `playground` source + a scheduled cleanup, vs. ephemeral in-memory/base64 returns for small
   results. Getting this wrong fills the site's file store with unreferenced blobs.
4. **Cost/telemetry for non-token modalities.** `RunOutcome` assumes input/output tokens. Image and
   TTS bill per image / per character. Either widen the ledger's notion of cost units or accept
   `cost` only.

**Frontend**

5. **Widen the type layer.** `PlaygroundConfig` gains a `modality` discriminant and a
   modality-specific params bag; `RunOutcome` gains optional `artifactUrl`, `artifactKind`,
   `transcript`, `extractedText`. Keep it a discriminated union so `executeRun` stays a single
   exhaustive switch.
6. **Widen the shell.** Decide the tab taxonomy (see Open Questions) and extend
   `PlaygroundShell`'s tab list; keep Single/Compare as a sub-toggle rather than flattening
   modality × layout into one tab row.
7. **A `MediaResultPanel`** sibling to `ResponsePanel`, rendering per artifact kind (image grid,
   `media-chrome` audio player, transcript block, extracted-text block).

*Deliverable:* nothing user-visible changes; every later phase becomes a mostly-declarative addition.

---

### Phase 1 — Image Generation Tab (highest value / lowest risk)

Backend already complete (`handle_generate_image`, models seeded). Purely additive.

- **Backend:** `run_image_sync(provider, model, prompt, size, quality, n)` shim from Phase 0.
- **Frontend:** `ImageConfigStrip` (model filtered to `Image`, size, quality, n) + prompt panel reuse +
  result grid with download and "open full size". Compare mode = same prompt against two models
  (`gpt-image-1` vs `gpt-image-1-mini` is the obvious first demo).
- **Reused:** prompt panel, run ledger, compare layout, trace rail.
- **Net new:** image grid component, size/quality controls.
- Risk: latency (10–60 s per image) — the existing synchronous run path may exceed gunicorn/proxy
  timeouts for `n>1`. Consider capping `n` or routing through the existing background-job path.

### Phase 2 — Audio Generation (TTS) Tab

Backend already complete (`handle_generate_audio`, `_resolve_tts_config`, ElevenLabs models seeded).

- **Backend:** `run_tts_sync(provider, model, input, voice, speed, response_format)`. Also expose a
  **voice catalogue** — `huf.ai.voice.api.list_voices(agent)` exists but is agent-scoped; the
  Playground needs a provider-scoped variant, otherwise the voice field is a free-text `Data` box
  (which is what `Agent.tts_voice` is today).
- **Frontend:** text input + voice picker (with preview) + model picker (`eleven_flash_v2_5` /
  `eleven_turbo_v2_5` / `eleven_multilingual_v2` / `tts-1*`) + speed slider + format selector →
  `media-chrome` player. Compare = same text, two voices or two models, two players.
- **Net new:** voice picker component; optional waveform (defer — a plain player is enough for v1).
- Risk: the voice-catalogue endpoint is the only real backend work; ElevenLabs and OpenAI voice
  lists have different shapes and need normalising.

### Phase 3 — Transcription (STT) + OCR / Document Understanding Tabs

Grouped because they share one interaction: **drop a file, get text back.**

- **Backend:** `run_stt_sync` is close to a rename of `huf.ai.audio_api.transcribe` with
  `create_message=False` and a provider+model override; `run_ocr_sync` wraps `handle_ocr_document`
  without message creation. `ocr_engine._determine_strategy` should surface *which* strategy it
  chose (local extractor / OCR endpoint / vision model) in the result — that is exactly the debug
  signal a playground exists to give.
- **Frontend:** a shared `FileDropPanel` (drag-drop + picker, respecting `audio_service.is_audio_file`
  and the OCR engine's supported types) → result pane with the transcript / extracted text, plus a
  metadata rail (model used, strategy, language, page count, duration).
- **Reused:** `speech-input.tsx` capture logic for a "record instead of upload" affordance in the STT tab.
- **Net new:** drop zone, strategy/metadata rail.
- Risk: file size limits and Frappe's upload path; private-file access control for the resulting `File`.

### Phase 4 — Realtime / Conversational Voice Tab (the hard one)

This is a different kind of work from Phases 1–3 and should not be scheduled as if it were the same.

**What exists:** the entire server-side control plane (session minting, engine abstraction,
credential brokering, Redis session stash, ASGI sidecar, persistence hooks).
**What does not exist:** *any* browser client. No PCM capture, no playback queue, no WS client, no
transcript UI, no session state machine. `huf-voice.md` says so explicitly.

- **Backend / ops:**
  - Make the sidecar a first-class, documented part of the dev and deploy story (Procfile entry or
    compose service; today it is an opt-in `pip install -e ".[realtime]"` + manual `python -m`).
  - Reverse-proxy config so `/voice/realtime/<session_id>` reaches port 8091 with WS upgrade intact.
  - Close the documented gaps that a playground will immediately expose: **user speech turns are not
    persisted** (a transcript pane showing only the agent's half is not a usable bench), and
    `send_to_session` raises on both engines (needed for "type a message into a live voice session",
    which both OpenAI and ElevenLabs playgrounds offer).
  - Decide whether realtime models become `AI Model` rows with modality `Speech-to-Speech`, or stay
    exclusively under `Voice Engine`. The Playground's model picker assumes the former.
- **Frontend:**
  - Mic capture at the provider's required PCM format (OpenAI Realtime wants PCM16 @ 24 kHz) —
    `MediaRecorder` alone is insufficient; needs `AudioWorklet` + a resampler. This is the single
    largest net-new frontend component.
  - Playback queue with barge-in (interrupt-on-user-speech) — both engines advertise
    `barge_in: True`, so the client must honour it.
  - Session state machine: idle → minting → connecting → live → ending → ended, with the sidecar's
    close codes (4404 expired session / 4500 misconfigured / 4502 upstream) surfaced as human errors.
  - Two client paths, because the two engines differ fundamentally: ElevenLabs gives a **signed URL
    to their servers** (and requires the client to echo `huf_conversation_id` as a dynamic variable —
    Huf cannot enforce this) while litellm_realtime gives a **path to Huf's own sidecar**. Abstract
    behind one `VoiceSession` interface with two transports; do not let engine specifics leak into
    the tab component.
  - Live interleaved transcript + input/output level meters + turn latency readout.

### Phase 5 (speculative) — Video, and cross-modality chaining

- `Agent Message.generated_video` and `kind: Video` already exist with no handler behind them.
  A `handle_generate_video` would complete the set, but there is no seeded video model and no
  provider story yet — park it until one exists.
- Chaining (image → OCR → prompt; prompt → TTS → STT round-trip as a quality check) is a natural
  playground superpower once each modality is individually benched. Explicitly **out of scope**
  until Phases 1–4 land.

---

## Open Questions & Risks

### Architectural risks

1. **Realtime transport is a different animal (biggest risk).** Frappe's chat streaming is
   REST + Socket.IO — server-push over a Node process, request/response for input. Realtime voice
   needs **duplex binary streaming with sub-200 ms budgets**. The team already concluded WSGI/gunicorn
   cannot host it and built a separate uvicorn sidecar, which means realtime voice introduces a
   **second long-lived server process, a second port, a second proxy rule, and a second failure
   mode** into every environment that wants the feature. That is an operational commitment, not a
   feature flag. Phase 4 should be gated on an explicit decision to own that.
2. **Two incompatible realtime engines.** ElevenLabs connects the browser *directly to ElevenLabs*
   (Huf sees nothing but the post-call webhook); litellm_realtime proxies through Huf's sidecar
   (Huf sees every frame). Observability, persistence, cost accounting and failure behaviour differ
   completely between them. A single "Realtime" playground tab that silently behaves differently per
   engine will confuse more than it reveals — surface the engine's `get_capabilities()` in the UI.
3. **Persistence asymmetry.** Realtime persists agent turns only; ElevenLabs persists nothing if the
   webhook misses. A playground built on top of this will intermittently show incomplete
   transcripts, and users will read that as a playground bug.
4. **Synchronous long-running generation.** Image generation and long TTS can exceed typical
   gunicorn worker / proxy timeouts. The text playground never hit this. Decide per modality:
   raise timeouts, or route through the existing background-job + Socket.IO completion pattern
   that chat already uses.
5. **`send_to_session` is dead code on every engine.** Anything in the plan that assumes mid-session
   text injection is currently unimplementable.

### Product / scope questions

6. **Tab taxonomy.** Modality × layout is a 2-D space (6 modalities × Single/Compare). Options:
   (a) modality tabs with a Single/Compare sub-toggle, (b) flat tab list, (c) modality as a
   `ConfigStrip` field with the tabs staying Single/Compare. (a) is recommended — it keeps the
   existing shell semantics and doesn't explode the tab row.
7. **Agent-mode vs direct-mode for media.** Text playground supports both ("run through this agent"
   vs "run this provider+model raw"). For media, agent-mode means the agent's
   `image_generation_model` / `tts_model` / `stt_model` is used and messages get persisted to a
   conversation. Is agent-mode in scope for media tabs, or is direct-mode enough for v1?
   Recommendation: direct-mode only for Phases 1–3; agent-mode is unavoidable for Phase 4 because
   voice sessions are minted *from* an Agent.
8. **Generated-artifact lifetime.** Do playground images/audio persist as `File` records the user can
   find later, or vanish on reload? Affects the run ledger (localStorage cannot hold blobs) and the
   site's disk usage. Needs a decision in Phase 0.
9. **Cost visibility.** Per-image and per-character pricing is not modelled — `AI Model` has
   `input_cost_per_1m_tokens` / `output_cost_per_1m_tokens` / `cached_input_cost_per_1m_tokens` only.
   Either extend the pricing fields or show latency-only for media runs.
10. **Voice catalogue ownership.** `Agent.tts_voice` is free-text `Data`. A picker needs a
    provider-scoped, cached voice list. Where does it live — a new `AI Voice` DocType, a cached
    provider call, or a hardcoded map per `provider_brand`?
11. **Permissions.** `audio_api.transcribe` gates `file_path` behind System Manager. What role gates
    playground media generation — is running image generation from the Playground a
    capability, and does it respect the same access checks agents do?
12. **Compare semantics for media.** Word-diff (`wordDiff.ts`) is meaningless for an image or an mp3.
    Compare for media is "put them next to each other and let the human judge" — which means the
    existing `evaluate_run` LLM-judge path also does not transfer without a vision/audio judge.

---

## Rough Effort Sizing

Deliberately coarse. Assumes one developer familiar with both the Frappe app and the React frontend.
"Weeks" are calendar-ish, not padded.

| Phase | Backend | Frontend | Total | Confidence |
| --- | --- | --- | --- | --- |
| **0 — Foundation** | Model-modality filter, 4 console shims, retention policy | Type widening, shell tabs, `MediaResultPanel` | **1–1.5 wk** | High — well-understood, no unknowns |
| **1 — Image** | Thin (shim only) | Config strip + result grid | **3–5 d** | High |
| **2 — TTS** | Voice catalogue endpoint (the real work) | Voice picker + player (media-chrome already installed) | **4–6 d** | Medium-high — voice list normalisation across providers is the unknown |
| **3 — STT + OCR** | Two shims + surface OCR strategy in result | Shared file-drop panel + metadata rail | **1 wk** | Medium-high |
| **4 — Realtime voice** | Sidecar productionisation, proxy/WS ops, user-turn persistence, `send_to_session`, realtime model modelling | PCM capture via AudioWorklet, playback queue + barge-in, session state machine, two transports, live transcript | **3–5 wk** | **Low** — the frontend audio pipeline and the two-engine split are both genuinely hard, and the ops story is unwritten |
| **5 — Video / chaining** | Unknown (no provider story) | — | Not sized | Speculative |

**Total for Phases 0–3 (all request/response modalities): ~3–4 weeks**, delivering image, TTS, STT
and OCR benches on top of infrastructure that already works.
**Phase 4 alone is comparable to or larger than Phases 0–3 combined**, and carries an operational
commitment (a second server process) that the others do not.

Recommended sequencing decision: ship 0→3 as one coherent release ("the Playground now covers every
modality Huf can do in a single request"), and treat Phase 4 as its own track with its own go/no-go,
rather than as the last item on this one.

---

## Appendix — Files to read first, in order

1. `huf/ai/voice/README.md` — the most honest document in the repo about what realtime does and does not do.
2. `huf/ai/handlers/media.py` — the four handlers all of Phases 1–3 wrap.
3. `huf/ai/voice/sidecar/app.py` (docstring, lines 1–60) — why the transport is what it is.
4. `frontend/src/components/playground/{types.ts,runExecutor.ts,PlaygroundShell.tsx}` — the three
   files every frontend phase touches.
5. `huf/ai/audio_api.py` — the template for what a clean console-layer media shim looks like.
6. `huf/install.py` (~lines 261–470) — the seeded model/modality ground truth.
