import { errorText, type FieldError, type WhatsAppError } from '@/services/whatsappApi';
import { headerSampleKey, type TemplateWizardDraft } from '../template/draft';
import { extractVariables } from '../template/variables';

/*
 * Backend field names are copied from huf/ai/gateway_adapters/whatsapp_templates.py
 * (validate_template_spec, _validate_buttons, _parse_named_samples, validate_create_payload)
 * and huf/ai/gateway_adapters/whatsapp_bridge.py (validate_create_payload, edit_template).
 * The validator writes list indexes as brackets (`buttons[0].url`); those are normalised to
 * dot paths (`buttons.0.url`) before matching.
 */

/** Backend field -> wizard field path, for fields that do not depend on the draft. */
const DIRECT: Record<string, string> = {
  template_name: 'name',
  language_code: 'language',
  body: 'body',
  footer: 'footer',
  ttl_seconds: 'ttl',
  category: 'category',
};

/** Button sub-field -> wizard button key. `example` depends on the button type. */
const BUTTON_FIELD: Record<string, (type: string) => string | null> = {
  text: () => 'text',
  url: () => 'url',
  phone_number: () => 'phoneNumber',
  example: (type) => (type === 'URL' ? 'urlExample' : 'codeExample'),
  type: () => null,
};

/**
 * Top-level error codes that come back without `errors[]` (no per-field list).
 * Maps the code to the backend field it concerns; `immutable_field` takes its field from the response.
 */
const TOP_LEVEL_FIELD: Record<string, string> = {
  invalid_name: 'template_name',
  template_name_taken_by_other_account: 'template_name',
  invalid_language: 'language_code',
  invalid_category: 'category',
};

export interface MappedErrors {
  /** Form field path -> message, ready to show next to the field. */
  fields: Record<string, string>;
  /** Messages that do not belong to a field the form shows. */
  general: string[];
}

const normalise = (field: string) => field.replace(/\[(\d+)\]/g, '.$1');

/** Own-property lookup, so a backend field such as `constructor` never reads Object.prototype. */
function own<T>(map: Record<string, T>, key: string): T | undefined {
  return Object.prototype.hasOwnProperty.call(map, key) ? map[key] : undefined;
}

function bodyTokens(draft: TemplateWizardDraft): string[] {
  return extractVariables(draft.body, draft.variableType);
}

/** Sample path for the header variable (text header) or the header media sample. */
function headerSamplePath(draft: TemplateWizardDraft): string {
  if (draft.header.type !== 'text') return 'header.mediaSample';
  const [token] = extractVariables(draft.header.text, draft.variableType);
  return token ? `samples.${headerSampleKey(token)}` : 'header.text';
}

/** Sample path for a body variable: `index` into the body's variables, or the first one. */
function bodySamplePath(draft: TemplateWizardDraft, index: number | null): string {
  const tokens = bodyTokens(draft);
  const token = tokens[index ?? 0];
  return token ? `samples.${token}` : 'body';
}

function pathFor(raw: string, draft: TemplateWizardDraft): string | null {
  const field = normalise(raw);
  const direct = own(DIRECT, field);
  if (direct) return direct;

  if (field === 'header') return draft.header.type === 'text' ? 'header.text' : 'header.mediaSample';
  if (field === 'sample' || field === 'header_named_samples' || field.startsWith('header_named_samples.')) {
    return headerSamplePath(draft);
  }

  if (field === 'sample_values' || field === 'named_samples') return bodySamplePath(draft, null);
  const indexed = /^(sample_values|named_samples)\.(\d+)(?:\.\w+)?$/.exec(field);
  if (indexed) return bodySamplePath(draft, Number(indexed[2]));
  const named = /^named_samples\.(\w+)$/.exec(field);
  if (named) {
    const name = named[1];
    return bodyTokens(draft).includes(name) ? `samples.${name}` : 'body';
  }

  if (field === 'buttons') return 'buttons';
  const button = /^buttons\.(\d+)(?:\.(\w+))?$/.exec(field);
  if (button) {
    const i = Number(button[1]);
    const sub = button[2];
    if (!sub || !draft.buttons[i]) return 'buttons';
    const mapped = own(BUTTON_FIELD, sub)?.(draft.buttons[i].type) ?? null;
    return mapped ? `buttons.${i}.${mapped}` : 'buttons';
  }

  // header_type, parameter_format, and send-time fields (header_params, body_params, button_params,
  // kind, link, caption) have no input in the wizard: they fall through to general notices.
  return null;
}

/**
 * Map backend `errors[]` (field, code, message) onto the wizard's field paths.
 * Unknown fields, and fields the wizard has no input for, are returned as general messages.
 */
export function mapBackendErrors(errors: readonly FieldError[], draft: TemplateWizardDraft): MappedErrors {
  const out: MappedErrors = { fields: {}, general: [] };
  for (const e of errors) {
    const path = pathFor(e.field, draft);
    if (!path) out.general.push(e.message);
    else if (!out.fields[path]) out.fields[path] = e.message;
  }
  return out;
}

/**
 * Field errors for a failed response. Uses `errors[]` when the backend sent it; otherwise turns a
 * top-level code (invalid_name, invalid_category, immutable_field, ...) into one field error so it
 * lands on the same field as a per-field error would. Returns [] for codes with no field.
 */
export function backendFieldErrors(res: WhatsAppError & { field?: string }): FieldError[] {
  if (res.errors?.length) return res.errors;
  const field = res.error === 'immutable_field' ? res.field : own(TOP_LEVEL_FIELD, res.error);
  if (!field) return [];
  return [{ field, code: res.error, message: res.message || errorText(res) }];
}
