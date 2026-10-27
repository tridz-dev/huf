import type { PreviewInput } from '../templateModel';

export type PreviewButtonType = 'QUICK_REPLY' | 'URL' | 'PHONE_NUMBER' | 'COPY_CODE';

export type PreviewHeader =
  | { kind: 'text'; text: string; sample?: string }
  | { kind: 'image' | 'video'; url?: string }
  | { kind: 'document'; filename?: string }
  | { kind: 'location' };

/** Sample values by position ({{1}} is index 0) or by name ({{first_name}}). */
export type PreviewVariables = readonly string[] | Readonly<Record<string, string>>;

export interface PreviewModel {
  header: PreviewHeader | null;
  body: string;
  samples?: PreviewVariables;
  footer?: string;
  buttons: { type: PreviewButtonType; text: string }[];
}

export type PreviewSample = 'marketing_default' | 'utility_default';

export const PREVIEW_SAMPLES: Record<PreviewSample, PreviewModel> = {
  marketing_default: {
    header: null,
    body: 'Hey there! Check out our fresh groceries now! Use code HEALTH to get additional 10% off on your entire purchase.',
    buttons: [
      { type: 'URL', text: 'Shop now' },
      { type: 'COPY_CODE', text: 'Copy code' },
    ],
  },
  utility_default: {
    header: null,
    body: "Good news! Your order 23KFEJ2312 has shipped! Here's your tracking information, please check link below.",
    buttons: [{ type: 'URL', text: 'Track shipment' }],
  },
};

/** Adapts the existing wizard/list input (unfilled body, raw samples) to the preview model. */
export function inputToPreviewModel(input: PreviewInput): PreviewModel {
  const type: string = input.headerType ?? '';
  const sample = (input.headerSample ?? '').trim();
  let header: PreviewHeader | null = null;
  if (type === 'TEXT' && input.header?.trim()) header = { kind: 'text', text: input.header, sample };
  else if (type === 'IMAGE' || type === 'VIDEO') header = { kind: type === 'IMAGE' ? 'image' : 'video', url: sample || undefined };
  else if (type === 'DOCUMENT') header = { kind: 'document', filename: sample || undefined };
  else if (type === 'LOCATION') header = { kind: 'location' };
  return {
    header,
    body: input.body,
    samples: input.samples,
    footer: input.footer?.trim() || undefined,
    buttons: (input.buttons ?? []).map((b) => ({ type: b.type, text: b.text.trim() || 'Button' })),
  };
}
