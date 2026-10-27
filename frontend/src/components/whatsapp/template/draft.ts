import type { VariableType } from './variables';

export type TemplateCategoryId = 'MARKETING' | 'UTILITY';
export type WizardHeaderType = 'none' | 'text' | 'image' | 'video' | 'document' | 'location';
export type WizardButtonType = 'QUICK_REPLY' | 'URL' | 'PHONE_NUMBER' | 'COPY_CODE';

export interface WizardHeader {
  type: WizardHeaderType;
  /** Header text; only used when type is "text". */
  text: string;
  /** Sample file link or uploaded path; used for image, video and document. */
  mediaSample: string;
}

export interface WizardButton {
  /** Stable key for list rendering and reordering. */
  id: string;
  type: WizardButtonType;
  text: string;
  /** URL buttons: the link; a trailing {{1}} makes it dynamic. */
  url: string;
  /** URL buttons with {{1}}: a full example link. */
  urlExample: string;
  /** Phone buttons: international number, e.g. +15551234567. */
  phoneNumber: string;
  /** Copy-code buttons: an example code. */
  codeExample: string;
}

/**
 * Wizard state for the three-step create/edit flow. Named TemplateWizardDraft
 * because `TemplateDraft` in whatsappApi is the saved draft record.
 *
 * `samples` keys: body variables use their token ("1", "first_name"); the header
 * variable uses "header." + token (see `headerSampleKey`).
 */
export interface TemplateWizardDraft {
  category: TemplateCategoryId;
  name: string;
  language: string;
  variableType: VariableType;
  header: WizardHeader;
  body: string;
  footer: string;
  buttons: WizardButton[];
  /** Message validity in seconds (Utility only); null keeps the WhatsApp default. */
  ttl: number | null;
  samples: Record<string, string>;
}

export const headerSampleKey = (token: string) => `header.${token}`;

export function emptyButton(type: WizardButtonType, id: string): WizardButton {
  return { id, type, text: '', url: '', urlExample: '', phoneNumber: '', codeExample: '' };
}

export function emptyDraft(category: TemplateCategoryId = 'MARKETING'): TemplateWizardDraft {
  return {
    category,
    name: '',
    language: 'en_US',
    variableType: 'number',
    header: { type: 'none', text: '', mediaSample: '' },
    body: '',
    footer: '',
    buttons: [],
    ttl: null,
    samples: {},
  };
}
