# ADR 0001: App Runtime Model and Capability Ownership

Status: Accepted
Date: 2026-08-24

## Context

Phase 0 of `docs/hub-orchestrator-unified-builder-plan.md` audited the existing
`HUF App` and `Agent`/`Agent Message` DocTypes (plan §A) and Phase 1 (plan §D,
§I) requires settling two open questions before any new tools or fields are
built: whether HUF needs multiple modality-specific App runtimes, and who owns
modality/capability configuration between `Agent` and `HUF App`.

## Decision 1: One generic Agent-backed App runtime

HUF will use a single generic, Agent-backed App runtime that is
capability-flagged, rather than building specialized per-modality App
runtimes (chat App, voice App, video App, etc.).

**Justification.** The plan's own audit already shows the App registry was
built capability-agnostic and the message pipeline was built modality-agnostic,
so a single runtime is not a new constraint but a recognition of what already
exists. `huf/huf/doctype/huf_app/huf_app.json`'s `launch_mode` field is a
Select with exactly one supported value, `"Route"`, today (plan lines 186-187),
meaning there is no existing precedent or plumbing for per-modality launch
paths to specialize against. Simultaneously, `Agent Message.kind` already
spans Text/Image/Audio/Video (plan line 826), so the chat/run pipeline that
every App routes through is already modality-agnostic at the schema level —
no schema changes to `Agent`, `Agent Message`, or `Agent Conversation` are
required to support new output modalities (plan lines 623-624). Building
separate runtimes per modality would duplicate this already-generic pipeline
for no behavioral gain, and would contradict the plan's Phase 1 recommendation
(plan lines 819-825) to keep one runtime and express variation purely through
capability flags.

## Decision 2: Capability configuration split — Agent vs. App

- **Agent-level** fields describe what the backend *can* do: existing fields
  such as `Agent.allow_file_upload`, `Agent.enable_ocr`, `Agent.tts_model`,
  `Agent.tts_voice`, and voice-engine selection (plan lines 869-877). These are
  unchanged by this work — Phase 8/9/11 only *surface* existing Agent
  capability at the App layer, they don't add new backend capability.
- **App-level** fields describe what *this App* exposes to its users: the new
  `HUF App.capabilities` Small Text (JSON) field introduced in plan §D.5
  (plan line 626) — a flat JSON blob of composable flags (file input, audio
  input, TTS output, video output, live voice) rather than five new booleans,
  because App capability composition is expected to grow (plan §D.10,
  referenced at line 626).

**Invariant.** An App's `capabilities` must always be a subset of what its
linked `Agent` supports — never a superset. An App cannot claim to expose TTS
output, audio input, OCR, or live voice unless the linked `Agent` record
already has the corresponding backend capability enabled (`Agent.tts_model`
set, `Agent.allow_file_upload`/STT configured, `Agent.enable_ocr` set, or a
configured voice engine, respectively). This mirrors the plan's framing of
Phase 8/9/11 as pure surfacing of already-implemented Agent capability (plan
lines 869-877) rather than App-level capability invention.

**Enforcement.** This subset invariant must be validated server-side at
`draft_app`/`update_app` time (plan §D.4/§I Phase 3a), rejecting any
`capabilities` payload that enables a flag the linked `Agent` does not itself
support, so App builder tools cannot create Apps that advertise capability
their backing Agent cannot deliver.

## Consequences

- No new App-runtime abstraction or per-modality routing code is needed;
  `install_app`/`AppsPage.tsx` continue to work unmodified for every modality
  (plan lines 855-857).
- `draft_app`/`update_app` need a capability-subset validation step against
  the linked Agent before persisting `HUF App.capabilities`.
- Future new Agent capabilities become available to Apps by adding a flag to
  the `capabilities` JSON blob, not by adding new App DocType fields or new
  runtimes.
