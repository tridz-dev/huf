import { describe, it, expect } from 'vitest';
import { isChatModel } from './chatModel';

describe('isChatModel', () => {
  it('keeps text and vision models and models with no modalities recorded', () => {
    for (const modalities of ['Text', 'Text,Vision', 'Text,Vision,Transcription', 'Vision', undefined, null, '']) {
      expect(isChatModel({ modalities })).toBe(true);
    }
  });
  it('drops embedding, image, speech and transcription models', () => {
    for (const modalities of ['Embeddings', 'Image', 'Text-to-Speech', 'Transcription', 'Speech-to-Speech', 'Video', 'OCR']) {
      expect(isChatModel({ modalities })).toBe(false);
    }
  });
});
