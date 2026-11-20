import type { VariableType } from './variables';

export type TemplateCategoryId = 'MARKETING' | 'UTILITY' | 'AUTHENTICATION';
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

/** One media card of a carousel template. */
export interface WizardCard {
  id: string;
  headerType: 'image' | 'video';
  /** Sample file link or uploaded path for the card header. */
  mediaSample: string;
  body: string;
  /** Example values for the card body's numbered variables, index 0 is {{1}}. */
  samples: string[];
  /** Quick-reply and website buttons only; every card needs the same kinds in the same order. */
  buttons: WizardButton[];
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
  /** Authentication only: add "For your security, do not share this code." */
  securityRecommendation: boolean;
  /** Authentication only: minutes the code is valid for; null shows no expiry line. */
  codeExpiryMinutes: number | null;
  /** Authentication only: label of the copy-code button. */
  otpButtonText: string;
  /** Marketing media carousel: body above a row of cards; no header, footer or top-level buttons. */
  carousel: boolean;
  cards: WizardCard[];
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
    securityRecommendation: true,
    codeExpiryMinutes: 10,
    otpButtonText: OTP_BUTTON_DEFAULT,
    carousel: false,
    cards: [],
  };
}

export function emptyCard(id: string, buttons: WizardButton[] = []): WizardCard {
  return { id, headerType: 'image', mediaSample: '', body: '', samples: [], buttons };
}

/** A new carousel card shaped like the first card (same button kinds), with empty text. */
export function newCardLike(first: WizardCard | undefined, id: string): WizardCard {
  const buttons = (first?.buttons ?? []).map((b, i) => ({ ...emptyButton(b.type, `${id}-b${i}`), text: '' }));
  return emptyCard(id, buttons);
}

export const OTP_BUTTON_DEFAULT = 'Copy code';
export const OTP_BODY = '{{1}} is your verification code.';
export const OTP_SECURITY = ' For your security, do not share this code.';
export const OTP_SAMPLE_CODE = '123456';

/**
 * Authentication templates have a fixed WhatsApp format, so the body, footer and the one
 * copy-code button are derived from the three options. Keeps preview and review honest.
 */
export function applyAuthenticationFormat(draft: TemplateWizardDraft): TemplateWizardDraft {
  if (draft.category !== 'AUTHENTICATION') return draft;
  const label = draft.otpButtonText.trim() || OTP_BUTTON_DEFAULT;
  const button = { ...emptyButton('COPY_CODE', 'otp-copy-code'), text: label, codeExample: OTP_SAMPLE_CODE };
  return {
    ...draft,
    header: { type: 'none', text: '', mediaSample: '' },
    body: OTP_BODY + (draft.securityRecommendation ? OTP_SECURITY : ''),
    footer: draft.codeExpiryMinutes === null ? '' : `This code expires in ${draft.codeExpiryMinutes} minutes.`,
    buttons: [button],
    variableType: 'number',
    ttl: null,
    samples: { '1': OTP_SAMPLE_CODE },
  };
}
