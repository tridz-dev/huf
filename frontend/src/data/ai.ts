export const MODEL_MODALITY_IMAGE = "Image";
export const MODEL_MODALITY_TTS = "Text-to-Speech";
export const MODEL_MODALITY_STT = "Transcription";

export const IMAGE_MODEL_LABEL = "Image Generation Model";
export const IMAGE_MODEL_PLACEHOLDER = "Select image model (optional)";
export const IMAGE_MODEL_DESCRIPTION =
  "Optional: Link specific Model for Image generation tool otherwise default model of the Agent's provider will be used";

export const TTS_MODEL_LABEL = "TTS Model";
export const TTS_MODEL_PLACEHOLDER = "Select TTS model (optional)";
export const TTS_MODEL_DESCRIPTION =
  "Specific model for Text-to-Speech (Audio Generation). If unset, defaults to the provider's default TTS model.";

export const TTS_VOICE_LABEL = "TTS Voice";
export const TTS_VOICE_PLACEHOLDER =
  "e.g. alloy, nova, 21m00Tcm4TlvDq8ikWAM";
export const TTS_VOICE_DESCRIPTION =
  "Voice to use for TTS (e.g. alloy, echo, onyx).";

export const STT_MODEL_LABEL = "Audio Transcription Model";
export const STT_MODEL_PLACEHOLDER = "Select transcription model (optional)";
export const STT_MODEL_DESCRIPTION =
  "Specific model for Audio Transcription (speech-to-text). If unset, defaults to the provider's default transcription model.";

/**
 * Canonical user-facing label for the audio transcription capability.
 * Backend category value is "Transcription" (Agent Tool Type / AI Model modality).
 */
export const AUDIO_TRANSCRIPTION_LABEL = "Audio Transcription";

/**
 * Tool type/category values that map to the Audio Transcription capability.
 * "Speech to Text" is the legacy value kept for backward compatibility with
 * saved documents.
 */
const AUDIO_TRANSCRIPTION_TOOL_TYPES: readonly string[] = [
  "Transcription",
  "Speech to Text",
];

/**
 * Display label for a tool type/category value. Aligns the audio
 * transcription naming (legacy "Speech to Text" and backend "Transcription")
 * to the canonical "Audio Transcription" label; everything else is unchanged.
 */
export function getToolTypeDisplayLabel(type: string): string {
  return AUDIO_TRANSCRIPTION_TOOL_TYPES.includes(type)
    ? AUDIO_TRANSCRIPTION_LABEL
    : type;
}

export const MOCK_PROVIDER_OPENAI = "openai";
export const MOCK_PROVIDER_ANTHROPIC = "anthropic";
export const MOCK_PROVIDER_GOOGLE = "google";

export const MOCK_MODEL_GPT4 = "gpt-4";
export const MOCK_MODEL_GPT35_TURBO = "gpt-3.5-turbo";
export const MOCK_MODEL_CLAUDE3_OPUS = "claude-3-opus";
export const MOCK_MODEL_CLAUDE3_SONNET = "claude-3-sonnet";
export const MOCK_MODEL_GEMINI_PRO = "gemini-pro";


