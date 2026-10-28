/**
 * Whether a model can hold a text conversation. Embedding, image, speech and transcription models are listed
 * on the Models page but cannot answer a prompt, so pickers that need a chat model leave them out.
 * A model with no modalities recorded is kept: nothing says it cannot chat.
 */
export function isChatModel(model: { modalities?: string | null }): boolean {
  const kinds = (model.modalities ?? '').split(',').map((k) => k.trim()).filter(Boolean);
  return kinds.length === 0 || kinds.includes('Text') || kinds.includes('Vision');
}
