// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { errorText, type FieldError, type WhatsAppError } from '@/services/whatsappApi';
import { emptyDraft, type TemplateWizardDraft } from '../template/draft';
import { addButton } from './draftActions';
import { backendFieldErrors, mapBackendErrors } from './backendErrors';

// Field names below are the literal strings the Python validators emit
// (huf/ai/gateway_adapters/whatsapp_templates.py and whatsapp_bridge.py), list indexes included.

/** Text header with one variable, body with two, and one URL, phone and copy-code button. */
function textDraft(): TemplateWizardDraft {
  let d: TemplateWizardDraft = {
    ...emptyDraft(),
    body: 'Hi {{1}}, order {{2}}',
    header: { type: 'text', text: 'Ref {{1}}', mediaSample: '' },
  };
  d = addButton(d, 'URL', 'a');
  d = addButton(d, 'PHONE_NUMBER', 'b');
  d = addButton(d, 'COPY_CODE', 'c');
  return d;
}

function namedDraft(): TemplateWizardDraft {
  return { ...emptyDraft(), variableType: 'name', body: 'Hi {{first_name}}, order {{order_id}}' };
}

function mediaDraft(): TemplateWizardDraft {
  return { ...emptyDraft(), body: 'Hi {{1}}', header: { type: 'image', text: '', mediaSample: '' } };
}

const failure = (error: string, extra: Record<string, unknown> = {}): WhatsAppError & { field?: string } => ({
  success: false,
  error,
  ...extra,
});

const one = (field: string, draft: TemplateWizardDraft) =>
  mapBackendErrors([{ field, code: 'c', message: `msg:${field}` }], draft).fields;

describe('mapBackendErrors: per-field errors from errors[]', () => {
  it.each<[string, string]>([
    ['template_name', 'name'],
    ['language_code', 'language'],
    ['body', 'body'],
    ['footer', 'footer'],
    ['ttl_seconds', 'ttl'],
    ['category', 'category'],
    ['header', 'header.text'],
    ['sample', 'samples.header.1'],
    ['header_named_samples[0]', 'samples.header.1'],
    ['header_named_samples[0].name', 'samples.header.1'],
    ['sample_values', 'samples.1'],
    ['sample_values[0]', 'samples.1'],
    ['sample_values[1]', 'samples.2'],
    ['buttons', 'buttons'],
    ['buttons[0]', 'buttons'],
    ['buttons[0].type', 'buttons'],
    ['buttons[0].text', 'buttons.0.text'],
    ['buttons[0].url', 'buttons.0.url'],
    ['buttons[0].example', 'buttons.0.urlExample'],
    ['buttons[1].phone_number', 'buttons.1.phoneNumber'],
    ['buttons[2].example', 'buttons.2.codeExample'],
    ['buttons[9].text', 'buttons'],
  ])('%s -> %s', (field, path) => {
    expect(one(field, textDraft())).toEqual({ [path]: `msg:${field}` });
  });

  it.each<[string, string]>([
    ['named_samples', 'samples.first_name'],
    ['named_samples[0]', 'samples.first_name'],
    ['named_samples[1].name', 'samples.order_id'],
    ['named_samples.first_name', 'samples.first_name'],
    ['named_samples.order_id', 'samples.order_id'],
    ['named_samples.unknown_var', 'body'],
  ])('named template: %s -> %s', (field, path) => {
    expect(one(field, namedDraft())).toEqual({ [path]: `msg:${field}` });
  });

  it.each<[string, string]>([
    ['sample', 'header.mediaSample'],
    ['header', 'header.mediaSample'],
    ['header_named_samples[0]', 'header.mediaSample'],
  ])('media header: %s -> %s', (field, path) => {
    expect(one(field, mediaDraft())).toEqual({ [path]: `msg:${field}` });
  });

  it('keeps the first message when two backend errors hit the same field', () => {
    const out = mapBackendErrors(
      [
        { field: 'buttons[0].url', code: 'invalid_url', message: 'first' },
        { field: 'buttons[0].url', code: 'too_long', message: 'second' },
      ],
      textDraft(),
    );
    expect(out.fields).toEqual({ 'buttons.0.url': 'first' });
  });
});

describe('mapBackendErrors: fields with no wizard input, or unknown fields, stay general', () => {
  it.each([
    'header_type',
    'parameter_format',
    'header_params[0]',
    'body_params[1]',
    'button_params[0].index',
    'kind',
    'link',
    'caption',
    'made_up_field',
  ])('%s is a general message', (field) => {
    const out = mapBackendErrors([{ field, code: 'c', message: `msg:${field}` }], textDraft());
    expect(out).toEqual({ fields: {}, general: [`msg:${field}`] });
  });
});

describe('backendFieldErrors: top-level codes without errors[]', () => {
  const draft = textDraft();

  it.each<[string, string, Record<string, unknown>]>([
    ['invalid_name', 'name', { message: 'Name must match ^[a-z0-9_]+$' }],
    ['invalid_language', 'language', { message: 'language_code is required' }],
    ['invalid_category', 'category', { message: 'Category must be one of MARKETING, UTILITY' }],
    ['template_name_taken_by_other_account', 'name', { message: 'Taken' }],
  ])('%s lands on %s', (code, path, extra) => {
    const res = failure(code, extra);
    expect(mapBackendErrors(backendFieldErrors(res), draft).fields).toEqual({ [path]: extra.message });
  });

  it.each<[string, string]>([
    ['language_code', 'language'],
    ['template_name', 'name'],
  ])('immutable_field with field %s lands on %s', (field, path) => {
    const res = failure('immutable_field', { field, message: 'Template name and language cannot be changed after creation.' });
    expect(mapBackendErrors(backendFieldErrors(res), draft).fields).toEqual({
      [path]: 'Template name and language cannot be changed after creation.',
    });
  });

  it('immutable_field on parameter_format is a general message', () => {
    const res = failure('immutable_field', { field: 'parameter_format', message: 'The variable format cannot be changed.' });
    expect(mapBackendErrors(backendFieldErrors(res), draft)).toEqual({
      fields: {},
      general: ['The variable format cannot be changed.'],
    });
  });

  it('a top-level code without a message falls back to the shared error text', () => {
    const res = failure('invalid_name');
    expect(backendFieldErrors(res)).toEqual([{ field: 'template_name', code: 'invalid_name', message: errorText(res) }]);
  });

  it.each(['edit_limit_24h', 'edit_limit_30d', 'create_failed', 'no_account', 'bridge_unavailable'])(
    '%s has no field and is not mapped',
    (code) => {
      expect(backendFieldErrors(failure(code, { message: 'x' }))).toEqual([]);
    },
  );

  it('prefers errors[] over the top-level code when both are present', () => {
    const errors: FieldError[] = [{ field: 'body', code: 'too_long', message: 'Body is too long.' }];
    expect(backendFieldErrors(failure('validation_failed', { errors, message: 'Body is too long.' }))).toEqual(errors);
  });
});
