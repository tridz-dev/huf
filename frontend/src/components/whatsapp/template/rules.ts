import { headerSampleKey, type TemplateWizardDraft, type WizardButton } from './draft';
import { isKnownLocale } from './locales';
import { findVariableTokens, hasStrayBraces, type VariableToken } from './variables';

// Kept free of runtime imports from the API service so this module stays pure.
const NAME_RE = /^[a-z0-9_]+$/;

export const WIZARD_LIMITS = {
  name: 512,
  headerText: 60,
  body: 1024,
  footer: 60,
  buttonText: 25,
  buttonsTotal: 10,
  urlButtons: 2,
  phoneButtons: 1,
  copyCodeButtons: 1,
  url: 2000,
  copyCode: 20,
  ttlMin: 30,
  ttlMax: 12 * 60 * 60,
} as const;

/** {fieldPath: message}. Paths: name, language, header.text, header.mediaSample, body, footer, buttons, buttons.<i>.<field>, ttl, samples.<key>. */
export type FieldErrors = Record<string, string>;

/** Lowercase, underscores for anything else, trimmed and capped: "Order Update!" -> "order_update". */
export function slugifyName(input: string): string {
  return input
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, WIZARD_LIMITS.name)
    .replace(/_+$/g, '');
}

export function validateName(name: string): string | null {
  if (!name.trim()) return 'Name is required.';
  if (!NAME_RE.test(name)) return 'Use only lowercase letters, digits and underscores.';
  if (name.length > WIZARD_LIMITS.name) return `Names are limited to ${WIZARD_LIMITS.name} characters.`;
  return null;
}

const looksLikePhone = (v: string) => /^[+\d\s().-]+$/.test(v) && (v.match(/\d/g) ?? []).length >= 7;
const looksLikeEmail = (v: string) => /\S+@\S+\.\S+/.test(v);

/** Problem with one sample value, or null. */
export function sampleProblem(value: string, variable: string): string | null {
  const v = value.trim();
  if (!v) return `Add an example for {{${variable}}}.`;
  if (looksLikePhone(v)) return 'Examples cannot look like a phone number.';
  if (looksLikeEmail(v)) return 'Examples cannot look like an email address.';
  return null;
}

const isHttpUrl = (v: string) => /^https?:\/\/[^\s/]+/i.test(v);
const isMediaSample = (v: string) => isHttpUrl(v) || v.startsWith('/files/') || v.startsWith('/private/files/');

function checkTokens(
  field: string,
  text: string,
  draft: TemplateWizardDraft,
  errors: FieldErrors,
  kind: 'header' | 'body',
): VariableToken[] {
  const tokens = findVariableTokens(text);
  if (hasStrayBraces(text) || tokens.some((t) => t.kind === 'invalid')) {
    errors[field] = 'Variables must look like {{1}} or {{first_name}}. Named variables use lowercase letters, digits and underscores, and start with a letter.';
    return tokens;
  }
  const wanted = draft.variableType;
  const wrong = tokens.find((t) => t.kind !== wanted);
  if (wrong) {
    errors[field] =
      wanted === 'number'
        ? 'This template uses numbered variables like {{1}}. Named variables cannot be mixed in.'
        : 'This template uses named variables like {{first_name}}. Numbered variables cannot be mixed in.';
    return tokens;
  }
  if (wanted === 'number') {
    const distinct = [...new Set(tokens.map((t) => Number(t.token)))].sort((a, b) => a - b);
    if (distinct.some((n, i) => n !== i + 1)) {
      errors[field] = 'Variables must be numbered {{1}}, {{2}}, ... without gaps.';
    }
  } else if (kind === 'body') {
    const names = tokens.map((t) => t.token);
    const dup = names.find((n, i) => names.indexOf(n) !== i);
    if (dup) errors[field] = `Each variable name can only be used once. {{${dup}}} appears more than once.`;
  }
  return tokens;
}

function validateButtons(buttons: readonly WizardButton[], errors: FieldErrors): void {
  const { buttonsTotal, urlButtons, phoneButtons, copyCodeButtons } = WIZARD_LIMITS;
  const count = (t: WizardButton['type']) => buttons.filter((b) => b.type === t).length;
  if (buttons.length > buttonsTotal) errors.buttons = `At most ${buttonsTotal} buttons are allowed.`;
  else if (count('URL') > urlButtons) errors.buttons = `At most ${urlButtons} website buttons are allowed.`;
  else if (count('PHONE_NUMBER') > phoneButtons) errors.buttons = 'Only one phone button is allowed.';
  else if (count('COPY_CODE') > copyCodeButtons) errors.buttons = 'Only one copy code button is allowed.';
  else {
    const quick = buttons.map((b) => b.type === 'QUICK_REPLY');
    const switches = quick.filter((q, i) => i > 0 && q !== quick[i - 1]).length;
    if (switches > 1) errors.buttons = 'Keep quick-reply buttons together and call-to-action buttons together.';
  }

  buttons.forEach((b, i) => {
    const p = `buttons.${i}`;
    const text = b.text.trim();
    if (!text) errors[`${p}.text`] = 'Button text is required.';
    else if (b.text.length > WIZARD_LIMITS.buttonText) {
      errors[`${p}.text`] = `Button text is limited to ${WIZARD_LIMITS.buttonText} characters.`;
    }
    if (b.type === 'URL') {
      const url = b.url.trim();
      const tokens = findVariableTokens(url);
      const dynamic = url.includes('{{');
      if (!isHttpUrl(url.replace(/\{\{[^{}]*\}\}/g, ''))) errors[`${p}.url`] = 'Enter a link starting with http:// or https://.';
      else if (url.length > WIZARD_LIMITS.url) errors[`${p}.url`] = `Links are limited to ${WIZARD_LIMITS.url} characters.`;
      else if (dynamic && (tokens.length !== 1 || tokens[0].token !== '1' || !url.endsWith('{{1}}') || hasStrayBraces(url))) {
        errors[`${p}.url`] = 'A link can only have a single {{1}} variable, at the very end.';
      } else if (dynamic) {
        const example = b.urlExample.trim();
        const prefix = url.slice(0, -'{{1}}'.length);
        if (!example) errors[`${p}.urlExample`] = 'Add an example link for the variable.';
        else if (example.includes(',')) errors[`${p}.urlExample`] = 'The example link cannot contain commas.';
        else if (!example.startsWith(prefix) || example === prefix) {
          errors[`${p}.urlExample`] = 'The example must start with the link above and add a value for {{1}}.';
        }
      }
    } else if (b.type === 'PHONE_NUMBER') {
      const phone = b.phoneNumber.replace(/[\s\-().]/g, '');
      if (!/^\+[1-9]\d{4,18}$/.test(phone)) {
        errors[`${p}.phoneNumber`] = 'Enter the number in international format, for example +15551234567.';
      }
    } else if (b.type === 'COPY_CODE') {
      const code = b.codeExample.trim();
      if (!code) errors[`${p}.codeExample`] = 'Add an example code.';
      else if (!/^[A-Za-z0-9]+$/.test(code) || code.length > WIZARD_LIMITS.copyCode) {
        errors[`${p}.codeExample`] = `The example code must be letters and digits only, up to ${WIZARD_LIMITS.copyCode} characters.`;
      }
    }
  });
}

/** Per-field errors for the whole draft; an empty object means it can be submitted. */
export function validateDraft(draft: TemplateWizardDraft): FieldErrors {
  const errors: FieldErrors = {};

  const nameProblem = validateName(draft.name);
  if (nameProblem) errors.name = nameProblem;
  if (!draft.language.trim()) errors.language = 'Choose a language.';
  else if (!isKnownLocale(draft.language)) errors.language = 'This language is not supported by WhatsApp.';

  // Header
  const sampleOwners: { key: string; token: string }[] = [];
  if (draft.header.type === 'text') {
    const text = draft.header.text;
    if (!text.trim()) errors['header.text'] = 'Header text is required.';
    else if (text.length > WIZARD_LIMITS.headerText) {
      errors['header.text'] = `Header text is limited to ${WIZARD_LIMITS.headerText} characters.`;
    } else {
      const tokens = checkTokens('header.text', text, draft, errors, 'header');
      if (!errors['header.text'] && tokens.length > 1) {
        errors['header.text'] = 'A text header allows at most one variable.';
      }
      if (!errors['header.text'] && tokens[0]) {
        sampleOwners.push({ key: headerSampleKey(tokens[0].token), token: tokens[0].token });
      }
    }
  } else if (['image', 'video', 'document'].includes(draft.header.type)) {
    const sample = draft.header.mediaSample.trim();
    if (!sample) errors['header.mediaSample'] = 'Add a sample file for the header.';
    else if (!isMediaSample(sample)) {
      errors['header.mediaSample'] = 'The sample must be an http(s) link or an uploaded file.';
    }
  }

  // Body
  const body = draft.body;
  if (!body.trim()) errors.body = 'Body is required.';
  else if (body.length > WIZARD_LIMITS.body) errors.body = `Body is limited to ${WIZARD_LIMITS.body} characters.`;
  else {
    const tokens = checkTokens('body', body, draft, errors, 'body');
    if (!errors.body) {
      const trimmed = body.trim();
      if (/^\{\{[^{}]*\}\}/.test(trimmed)) errors.body = 'The message cannot start with a variable. Add some text before it.';
      else if (/\{\{[^{}]*\}\}$/.test(trimmed)) errors.body = 'The message cannot end with a variable. Add some text after it.';
    }
    if (!errors.body) {
      for (const t of tokens) {
        if (!sampleOwners.some((o) => o.key === t.token)) sampleOwners.push({ key: t.token, token: t.token });
      }
    }
  }

  // Samples
  for (const { key, token } of sampleOwners) {
    const problem = sampleProblem(draft.samples[key] ?? '', token);
    if (problem) errors[`samples.${key}`] = problem;
    else if (draft.variableType === 'number' && (draft.samples[key] ?? '').includes(',')) {
      errors[`samples.${key}`] = 'Examples cannot contain commas.';
    }
  }

  // Footer
  if (draft.footer.length > WIZARD_LIMITS.footer) errors.footer = `Footer is limited to ${WIZARD_LIMITS.footer} characters.`;
  else if (draft.footer.includes('{{')) errors.footer = 'The footer cannot contain variables.';

  validateButtons(draft.buttons, errors);

  // TTL
  if (draft.ttl !== null) {
    if (draft.category !== 'UTILITY') errors.ttl = 'Message validity can only be set on Utility templates.';
    else if (!Number.isInteger(draft.ttl) || draft.ttl < WIZARD_LIMITS.ttlMin || draft.ttl > WIZARD_LIMITS.ttlMax) {
      errors.ttl = 'Message validity must be between 30 seconds and 12 hours.';
    }
  }
  return errors;
}

export function canSubmit(draft: TemplateWizardDraft): boolean {
  return Object.keys(validateDraft(draft)).length === 0;
}

/** Wizard steps and which error paths belong to each, so the UI can flag a step. */
export const WIZARD_STEPS = ['type', 'setup', 'content'] as const;
export type WizardStep = (typeof WIZARD_STEPS)[number];

export function stepOfField(path: string): WizardStep {
  if (path === 'category') return 'type';
  if (path === 'name' || path === 'language') return 'setup';
  return 'content';
}
