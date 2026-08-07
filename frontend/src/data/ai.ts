export const MODEL_MODALITY_IMAGE = "Image";

export const IMAGE_MODEL_LABEL = "Image Generation Model";
export const IMAGE_MODEL_PLACEHOLDER = "Select image model (optional)";
export const IMAGE_MODEL_DESCRIPTION =
  "Optional: Link specific Model for Image generation tool otherwise default model of the Agent's provider will be used";

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


