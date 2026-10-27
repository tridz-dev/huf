import { renderWhatsAppFormatting, type FormatSegment } from './formatting';
import type { TemplateWizardDraft, WizardButtonType, WizardHeaderType } from './draft';
import { headerSampleKey } from './draft';
import { fillDraftVariables } from './variables';

export interface WizardPreview {
  header:
    | { kind: 'text'; segments: FormatSegment[] }
    | { kind: 'media'; media: Exclude<WizardHeaderType, 'none' | 'text'>; url: string }
    | null;
  body: FormatSegment[];
  footer: string;
  buttons: { type: WizardButtonType; text: string }[];
}

/** Preview of the draft with sample values filled in (unfilled variables stay visible). */
export function buildWizardPreview(draft: TemplateWizardDraft): WizardPreview {
  const { header } = draft;
  let out: WizardPreview['header'] = null;
  if (header.type === 'text' && header.text.trim()) {
    const text = fillDraftVariables(header.text, draft.samples, headerSampleKey(''));
    out = { kind: 'text', segments: [{ text }] }; // headers do not support formatting
  } else if (header.type !== 'none' && header.type !== 'text') {
    out = { kind: 'media', media: header.type, url: header.mediaSample.trim() };
  }
  return {
    header: out,
    body: renderWhatsAppFormatting(fillDraftVariables(draft.body, draft.samples)),
    footer: draft.footer.trim(),
    buttons: draft.buttons.map((b) => ({ type: b.type, text: b.text.trim() || 'Button' })),
  };
}
