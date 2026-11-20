import type { WizardPayloadButton, ButtonParam } from '../whatsappApi';

export interface WizardPayloadCard {
  header_type: 'IMAGE' | 'VIDEO';
  /** Header example media: link or uploaded path. */
  sample: string;
  body: string;
  /** Numbered body variable examples, comma-joined. */
  sample_values?: string;
  buttons: WizardPayloadButton[];
}

export type HeaderParam =
  | string
  | { type: 'image' | 'document' | 'video'; link: string; filename?: string }
  | { type: 'document'; file: string }; // a private Frappe File, uploaded server-side
export interface CarouselCardDef {
  header_type: string;
  body_vars: string[];
  buttons: { type: string; dynamic: boolean; text?: string; url?: string; example?: string }[];
  /** Stored card text, examples and header handle (present on detail views). */
  body?: string;
  sample_values?: string[];
  header_example?: string;
}
/** Per-card values for a carousel send: header media by link or uploaded media id. */
export interface CarouselCardParam {
  header: { type?: 'image' | 'video'; link?: string; id?: string };
  body: string[];
  buttons: ButtonParam[];
}

export interface WizardAuthenticationFields {
  /** Authentication only: fixed WhatsApp format options. */
  add_security_recommendation?: boolean;
  code_expiration_minutes?: number;
  otp_button_text?: string;
}

export interface SendTemplateArgs {
  /** The Gateway to send from; its WhatsApp account is used, never one chosen by the caller. */
  gateway_name: string;
  to: string;
  template_name: string;
  body_params?: string[];
  header_params?: HeaderParam[];
  button_params?: ButtonParam[];
  carousel_params?: CarouselCardParam[];
}
