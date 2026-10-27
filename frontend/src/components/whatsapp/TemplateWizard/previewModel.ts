import type { PreviewModel } from '../TemplatePreview';
import { headerSampleKey, type TemplateWizardDraft } from '../template/draft';
import { extractVariables, fillDraftVariables } from '../template/variables';

/** The draft as the customer would see it: header text filled in, body samples by position or name. */
export function draftToPreviewModel(draft: TemplateWizardDraft): PreviewModel {
  const { header } = draft;
  const media = header.mediaSample.trim();
  let previewHeader: PreviewModel['header'] = null;
  if (header.type === 'text' && header.text.trim()) {
    previewHeader = { kind: 'text', text: fillDraftVariables(header.text, draft.samples, headerSampleKey('')) };
  } else if (header.type === 'image' || header.type === 'video') {
    previewHeader = { kind: header.type, url: media || undefined };
  } else if (header.type === 'document') {
    previewHeader = { kind: 'document', filename: media.split('/').pop() || undefined };
  } else if (header.type === 'location') {
    previewHeader = { kind: 'location' };
  }

  let samples: PreviewModel['samples'];
  if (draft.variableType === 'name') {
    samples = draft.samples;
  } else {
    const list: string[] = [];
    for (const token of extractVariables(draft.body, 'number')) list[Number(token) - 1] = draft.samples[token] ?? '';
    samples = Array.from(list, (v) => v ?? '');
  }
  return {
    header: previewHeader,
    body: draft.body,
    samples,
    footer: draft.footer.trim() || undefined,
    buttons: draft.buttons.map((b) => ({ type: b.type, text: b.text.trim() || 'Button' })),
  };
}
