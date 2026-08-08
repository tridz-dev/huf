# Audio Tool Findings

## Executive Summary

HUF already has the bones for audio:

- Browser recording and speech input in chat.
- Server upload and transcription endpoints.
- A LiteLLM-backed `transcribe_audio` tool.
- Dedicated `Agent.stt_model`, `Agent.tts_model`, and `Agent.tts_voice` fields.
- `Agent Message` fields for `voice_message`, `generated_audio`, `stt_model`,
  `tts_model`, and `tts_voice`.
- TTS via `generate_audio`.

The main problem is not absence. It is fragmentation.

Audio currently enters HUF through different doors:

- Browser Web Speech API directly fills the text box.
- Browser MediaRecorder uploads audio to HUF for STT.
- Agent tools can call `transcribe_audio`.
- Legacy Frappe `Agent Chat` form has its own audio send path.
- Old provider-specific transcription settings still exist.

The fix should be to standardize a single backend audio capability and let chat,
agent tools, API clients, and later flows/workspaces call that same capability
with different wrappers.

## Current Capabilities

### 1. Chat UI Speech Input

File: `frontend/src/components/ai-elements/speech-input.tsx`

There are two client modes:

- `speech-recognition`: uses browser `SpeechRecognition` /
  `webkitSpeechRecognition`; final transcript is appended directly to the input.
- `media-recorder`: uses `navigator.mediaDevices.getUserMedia` and
  `MediaRecorder`; sends an audio blob to a caller-provided `onAudioRecorded`
  callback.

Important behavior:

- Web Speech API mode does not use HUF STT at all.
- MediaRecorder mode depends on the parent component to upload and transcribe.
- Recorded MIME is forced to `audio/webm`.
- No explicit max duration is enforced in this React component.

### 2. React Chat Upload and Transcribe

Files:

- `frontend/src/components/chat/ChatInput.tsx`
- `frontend/src/services/chatApi.ts`

`ChatInput.handleAudioRecorded`:

1. Creates `recording-{timestamp}.webm`.
2. Converts the blob to base64.
3. Calls `transcribeAudio`.
4. Inserts the transcript into the visible chat as a user message.
5. Calls the normal agent send path with the transcript.

`transcribeAudio` calls:

```text
huf.ai.agent_chat.upload_audio_and_transcribe_web
```

with:

```text
transcribe_only: true
```

So the current React flow is:

```text
audio blob -> upload/transcribe -> transcript -> send text to agent
```

Audio is preserved as `voice_message`, but the agent run receives text.

### 3. Backend Web Audio Endpoint

File: `huf/ai/agent_chat.py`

`upload_audio_and_transcribe_web`:

- validates filename and base64 data
- decodes bytes
- creates a conversation when needed
- creates an `Agent Message` with `kind = Audio`
- saves the uploaded audio as a Frappe `File`
- stores the file URL in `Agent Message.voice_message`
- calls `sdk_tools.handle_transcribe_audio`
- updates the user message content with the transcript
- either returns transcript only or runs the agent with the transcript

This endpoint is useful, but it mixes several concerns:

- upload
- message creation
- STT execution
- optional agent run
- conversation creation

That makes it convenient for chat but awkward as a reusable API primitive.

### 4. Installed Agent Tool: `transcribe_audio`

Files:

- `huf/install.py`
- `huf/ai/sdk_tools.py`

`create_transcribe_audio_tool` installs or updates an `Agent Tool Function`
named `transcribe_audio`.

It points to:

```text
huf.ai.sdk_tools.handle_transcribe_audio
```

Parameters:

- `file_id`
- `file_url`
- `language`
- `model`

Tool type:

```text
Transcription
```

But the created tool has `types = "Custom Function"`, while frontend TypeScript
still includes a `ToolType` option named `"Speech to Text"`. This naming is not
fully standardized.

### 5. LiteLLM STT Resolution

File: `huf/ai/sdk_tools.py`

`_resolve_stt_config` priority:

1. Tool-call `model`.
2. `Agent.stt_model`.
3. Provider default.

Provider defaults:

| Provider | Default |
|---|---|
| OpenAI | `whisper-1` |
| Azure | `whisper-1` |
| Groq | `groq/whisper-large-v3` |
| Deepgram | `deepgram/nova-2` |
| Fallback | `whisper-1` |

The dedicated `Agent.stt_model` path is the cleanest design element here. It
allows the main conversation model and STT model to be different providers.

### 6. Gemini/Google Special Case

File: `huf/ai/sdk_tools.py`

For provider names `google`, `gemini`, or `vertex_ai`, transcription is handled
through a `litellm.completion` call with base64 audio embedded as a data URL.

This is a workaround for models that can process audio through multimodal
completion rather than a normal transcription endpoint.

Problem:

- The content block uses `"image_url"` for audio data.
- This works only if the target provider/model tolerates that shape.
- It blurs "transcription" and "audio-capable chat completion."

This needs a named provider capability strategy, not hidden branching inside the
tool.

### 7. TTS / Audio Generation

Files:

- `huf/install.py`
- `huf/ai/sdk_tools.py`
- `frontend/src/components/chat/ChatMessage.tsx`
- `frontend/src/components/ai-elements/audio-player.tsx`

`generate_audio` is installed as a tool and points to:

```text
huf.ai.sdk_tools.handle_generate_audio
```

It uses LiteLLM `speech()`, saves generated audio as a Frappe file, creates an
`Agent Message` with `kind = Audio`, stores `generated_audio`, and emits a
socket event.

The frontend renders assistant `generatedAudio` with a `media-chrome` audio
player.

This path is more first-class than voice input because generated audio appears
as an assistant artifact/message, not only as text.

### 8. Legacy Provider Settings Path

Files:

- `huf/ai/transcription_handler.py`
- `huf/huf/doctype/openai_settings/openai_settings.py`
- `huf/huf/doctype/groq_settings/groq_settings.py`
- `frontend/src/components/settings/VoiceSettingsTab.tsx`

This path dispatches to provider-specific settings doctypes:

```text
{Provider} Settings.transcribe_audio()
```

OpenAI and Groq settings implement direct HTTP transcription APIs. The UI allows
API URL, method, auth type, file param, and response path configuration.

This seems older than the LiteLLM path. It may still be useful for arbitrary
HTTP transcription providers, but it competes with `AI Provider` + `AI Model`
as the main capability model.

### 9. Legacy Frappe Agent Chat Form

Files:

- `huf/huf/doctype/agent_chat/agent_chat.js`
- `huf/ai/agent_chat.py`

The desk form records audio with `MediaRecorder`, limits recording to 3 minutes,
calls `upload_audio_and_transcribe`, and directly appends transcript/run output
to the desk chat UI.

This path is older and has different UX from the React chat path.

### 10. Standalone Web Agent Chat

File: `huf/www/agent_chat.html`

This standalone HTML chat records audio, calls
`upload_audio_and_transcribe_web`, and then refreshes history. It treats audio
messages as playable audio entries in the UI.

## Use Cases

### Chat Dictation

User speaks instead of typing. The transcript fills the input box or is sent
directly.

Current support:

- Browser Web Speech API fills input.
- MediaRecorder can upload to HUF and send transcript.

Gap:

- Browser speech recognition bypasses HUF provider/model/audit/cost controls.
- Behavior differs by browser.

### Voice Message to Agent

User sends a voice note as the actual message.

Current support:

- React chat records, transcribes, and sends transcript.
- Raw audio is saved as `voice_message`.

Gap:

- Agent receives transcript only.
- The raw audio is not part of the formal run input contract.
- UI mostly displays transcript, not a combined "audio + transcript" message.

### Uploaded Audio File Transcription

User uploads an audio file and asks the agent to transcribe/summarize it.

Current support:

- Agent can call `transcribe_audio` if the audio file is already a Frappe File.

Gap:

- General file upload path is OCR/document-oriented.
- Audio upload is not clearly routed to STT in the attachment pipeline.

### Agent-Initiated Transcription

Agent receives a `file_id`/`file_url` and decides to call `transcribe_audio`.

Current support:

- Installed tool exists.

Gap:

- Tool type naming and UI affordance are inconsistent.
- The tool creates/updates `Agent Message` as a side effect when
  `conversation_id` is present. Tool execution and message creation are coupled.

### Public API Transcription

External app calls HUF to transcribe an audio file.

Current support:

- Can call whitelisted methods.

Gap:

- No clean dedicated `/audio/transcriptions` style API.
- Existing endpoint also creates conversations/messages and can run agents.

### Flow / Workspace Audio Step

A future flow/workspace step asks for voice input, transcribes it, then advances
to the next stage.

Current support:

- Reusable backend logic exists.

Gap:

- No independent audio job/result object.
- No status lifecycle for long transcription.
- No clean separation between artifact, transcript, and agent message.

### Agent Generates Audio Reply

Agent uses TTS to produce voice narration or a spoken answer.

Current support:

- `generate_audio` tool.
- Dedicated TTS model and voice fields.
- Chat renders generated audio.

Gap:

- Cost/usage accounting for audio generation is not clearly normalized with LLM
  token accounting.
- User voice messages are less richly rendered than assistant generated audio.

## Main Gaps

### 1. Two STT Architectures

There is a LiteLLM `AI Provider` / `AI Model` path and a legacy provider
settings path.

Recommendation:

- Make LiteLLM + `AI Model.modalities = Transcription` the canonical path.
- Keep legacy provider settings only as an "Advanced HTTP STT adapter" if truly
  needed.
- Do not expose both as equal concepts in normal UI.

### 2. Audio Is Not a First-Class Run Input

Current chat converts audio to text before calling the agent.

Recommendation:

- Keep transcript-first execution for MVP.
- But define an input envelope that preserves source audio:

```json
{
  "type": "audio_message",
  "file_id": "...",
  "file_url": "...",
  "transcript": "...",
  "language": "auto",
  "stt_model": "...",
  "transcription_status": "completed"
}
```

The agent prompt can still receive text, but the run/message record should know
it came from audio.

### 3. Endpoint Coupling

`upload_audio_and_transcribe_web` does upload, conversation creation, message
creation, transcription, and optional run.

Recommendation:

Split internally into:

- `save_audio_file(...)`
- `transcribe_audio_file(...)`
- `create_audio_message(...)`
- `run_agent_with_transcript(...)`

Then keep the existing whitelisted endpoint as a compatibility wrapper.

### 4. Inconsistent Naming

Names currently include:

- `Speech to Text`
- `Transcription`
- `STT`
- `Audio Transcription`
- `transcribe_audio`
- `handle_speech_to_text`

Recommendation:

- User-facing capability: `Audio Transcription`.
- Tool function: `transcribe_audio`.
- Model modality: `Transcription`.
- Internal abbreviation: `stt` only in fieldnames like `stt_model`.
- Retire `Speech to Text` from new UI labels unless needed for compatibility.

### 5. Tool Side Effects

`handle_transcribe_audio` can create/update `Agent Message` records and emit
socket events.

Recommendation:

- Core transcription service should return transcript only.
- Chat wrapper should decide whether to create/update messages.
- Agent tool wrapper can optionally attach result metadata to the run, but
  should not surprise-create user messages unless explicitly requested.

### 6. Provider Capability Detection

`AI Model.modalities` exists and Agent validation checks `Transcription`, but
default provider STT behavior still uses a small hardcoded map.

Recommendation:

- Use `AI Model.modalities` as the main picker/filter.
- Seed known STT models.
- Provider defaults should point to actual `AI Model` records where possible.
- Add validation that the selected STT model belongs to a provider with an API
  key.

### 7. Browser Web Speech Bypass

Web Speech API mode transcribes outside HUF. This is fast, but it avoids HUF's
provider controls, audit trail, and data-governance story.

Recommendation:

- Make it a configurable "local/browser dictation" mode.
- Default serious/business agent chat to server STT when `stt_model` exists.
- Label browser dictation as draft input, not an audited transcription.

### 8. Missing Hardening

Needed checks:

- max audio file size
- max duration
- MIME allowlist
- extension sniffing
- private/public file policy
- per-agent audio permission
- rate limits
- transcript length limits
- clear error codes
- cleanup behavior for failed/stale audio messages

The desk form has a 3-minute UI timer; React MediaRecorder currently does not.

## Recommended Design

### Canonical Backend Service

Create a small service module, for example:

```text
huf/ai/audio_service.py
```

Core functions:

```text
save_audio_upload(filename, b64data, *, attached_to_doctype=None, attached_to_name=None)
resolve_stt_config(agent_name, model=None)
transcribe_audio_file(file_id, *, agent_name, language=None, model=None)
create_audio_user_message(conversation_id, file_id, transcript, metadata)
generate_audio_message(...)
```

Keep `sdk_tools.handle_transcribe_audio` but make it call this service.

### Canonical API Shape

For API/SDK use:

```text
huf.ai.audio_api.transcribe
```

Inputs:

| Field | Required | Notes |
|---|---:|---|
| `file_id` | one of | Preferred existing Frappe file |
| `b64data` + `filename` | one of | Upload and transcribe |
| `agent` | yes | Determines STT model/provider |
| `conversation` | no | Attach result to conversation if provided |
| `language` | no | Provider-specific |
| `model` | no | Explicit override |
| `create_message` | no | Default false for API, true for chat wrapper |

Output:

```json
{
  "success": true,
  "transcript": "...",
  "file_id": "...",
  "file_url": "...",
  "message_id": "...",
  "stt_model": "...",
  "provider": "...",
  "language": "auto-detected",
  "duration_ms": null
}
```

### Chat Path

React chat should call a chat-specific wrapper:

```text
record -> audio_api.transcribe(create_message=true) -> send transcript
```

But the displayed user message should preserve:

- playable audio
- transcript
- STT model
- language
- error/retry state

### Agent Tool Path

`transcribe_audio` should become a thin tool wrapper:

```text
file_id/file_url -> audio_service.transcribe_audio_file -> transcript result
```

It should return structured output:

```json
{
  "success": true,
  "text": "...",
  "file_id": "...",
  "model": "...",
  "provider": "..."
}
```

Message creation should be opt-in.

### Provider Strategy

Provider support should be expressed in three layers:

1. `AI Model.modalities` includes `Transcription`.
2. `Agent.stt_model` selects a model.
3. Provider-specific adapter is chosen by LiteLLM capability or explicit adapter
   class.

Known paths:

- OpenAI/Groq/Deepgram: `litellm.transcription`
- Gemini/Google/Vertex: multimodal completion adapter until LiteLLM has a
  cleaner transcription route
- Custom HTTP STT: optional adapter, not the normal path

## MVP Fix Plan

### Phase 1 - Standardize Without Breaking UI

- Add `huf/ai/audio_service.py`.
- Move common upload and STT logic into it.
- Keep `upload_audio_and_transcribe_web` unchanged externally.
- Make `handle_transcribe_audio` call the service.
- Add size/MIME/duration guardrails.
- Normalize return fields to `transcript` and keep `text` as compatibility alias.

### Phase 2 - Clean Tool and UI Naming

- Align tool type labels around `Audio Transcription`.
- Keep `Transcription` as model modality.
- Update frontend type union from `Speech to Text` to include the real current
  tool categories.
- In agent settings, keep `STT Model` but describe it as "Audio Transcription
  Model."

### Phase 3 - Improve Chat Audio Message

- Render user `voiceMessage` audio in React chat.
- Show transcript below the player.
- Add retry transcription action for failed/empty transcript.
- Add React MediaRecorder duration cap matching or improving the desk 3-minute
  cap.

### Phase 4 - API and Flow Readiness

- Add clean whitelisted audio API.
- Add an audio result envelope usable by flow/workspace steps.
- Add tests for direct API, chat wrapper, and tool wrapper.

## Open Questions

- Should browser Web Speech API stay enabled by default, or only as a fallback?
- Should audio files be private by default?
- Should `transcribe_audio` be available to every agent by default, or only when
  explicitly attached?
- Should generated audio be considered an assistant message, an artifact, or
  both?
- Do we want an `Audio Job` DocType for long files, or keep synchronous MVP?

## Opinionated Recommendation

For MVP, do not build a heavy audio subsystem.

Do this instead:

1. Keep transcript-first agent execution.
2. Make audio metadata first-class in `Agent Message`.
3. Extract one canonical audio service.
4. Keep old endpoints as wrappers.
5. Use `Agent.stt_model` and `AI Model.modalities = Transcription` as the
   product-facing configuration.
6. Treat provider settings HTTP transcription as advanced/legacy unless a real
   provider cannot work through LiteLLM.

This gives HUF a coherent audio story without adding a large new surface area.

