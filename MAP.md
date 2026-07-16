# MAP - Audio Tool

Exploration track for HUF audio input, speech-to-text, and related audio tool
design. This mirrors the lightweight WorkspaceUI track style: local markdown
first, code-grounded findings, then implementation tickets once the target
shape is locked.

## Destination

A settled HUF audio contract that lets chat UI, agent tools, API clients, and
future flow/workspace surfaces use audio consistently.

Done means:

- The current audio/STT/TTS paths are mapped.
- The gap between chat preprocessing, agent tool execution, and public API usage
  is explicit.
- A minimal design is chosen for one canonical audio transcription service.
- Follow-up implementation tickets can be written without more discovery.

## Snapshot

Repo inspected: `tridz-dev/huf` on `develop`, commit
`95daa90a8fc356086cb56288e29eacd84eea97b2`.

Primary files:

- `huf/ai/agent_chat.py`
- `huf/ai/sdk_tools.py`
- `huf/ai/transcription_handler.py`
- `huf/install.py`
- `huf/huf/doctype/agent/agent.json`
- `huf/huf/doctype/agent_message/agent_message.json`
- `huf/huf/doctype/ai_model/ai_model.json`
- `huf/huf/doctype/openai_settings/openai_settings.py`
- `huf/huf/doctype/groq_settings/groq_settings.py`
- `frontend/src/components/chat/ChatInput.tsx`
- `frontend/src/components/ai-elements/speech-input.tsx`
- `frontend/src/components/chat/ChatMessage.tsx`
- `frontend/src/services/chatApi.ts`
- `frontend/src/components/settings/VoiceSettingsTab.tsx`
- `frontend/src/hooks/useChatSocket.tsx`
- `frontend/src/components/chat/chatMessageList.mappers.ts`
- `huf/www/agent_chat.html`
- `huf/huf/doctype/agent_chat/agent_chat.js`

## Current Understanding

HUF has real audio capability today, but it is split across several pathways.

The strongest current path is LiteLLM-backed:

- `transcribe_audio` installed by `huf/install.py`
- function path: `huf.ai.sdk_tools.handle_transcribe_audio`
- provider/model resolution through `Agent.stt_model`, tool `model`, or provider
  default.

The chat UI path records audio, uploads it, transcribes it, and then sends the
transcript as a normal text message to the agent.

The older provider settings path still exists:

- `huf/ai/transcription_handler.py`
- `OpenAISettings.transcribe_audio`
- `GroqSettings.transcribe_audio`
- `VoiceSettingsTab`

This creates two mental models: "audio as a pre-chat conversion" and "audio as
an agent tool/capability." They should be unified.

## Documents

- [FINDINGS.md](FINDINGS.md) - full context, use cases, gaps, and recommended
  design.

## Proposed Frontier

- Canonical audio service contract.
- Chat/API endpoint consolidation.
- Tool schema cleanup and naming normalization.
- Provider/model capability registry.
- Frontend audio UX and socket event hardening.
- Security and operational limits.
