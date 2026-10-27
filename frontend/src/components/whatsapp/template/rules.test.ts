import { describe, expect, it } from 'vitest';
import { emptyButton, emptyDraft, type TemplateWizardDraft, type WizardButton, type WizardButtonType } from './draft';
import { canSubmit, sampleProblem, slugifyName, stepOfField, validateDraft, validateName } from './rules';

function valid(over: Partial<TemplateWizardDraft> = {}): TemplateWizardDraft {
  return { ...emptyDraft('MARKETING'), name: 'summer_sale', body: 'Hello there', ...over };
}
function btn(type: WizardButtonType, over: Partial<WizardButton> = {}): WizardButton {
  return { ...emptyButton(type, `${type}-${Math.random()}`), text: 'Go', ...over };
}
const url = (over: Partial<WizardButton> = {}) => btn('URL', { url: 'https://example.com/x', ...over });
const phone = () => btn('PHONE_NUMBER', { phoneNumber: '+15551234567' });
const quick = () => btn('QUICK_REPLY');

describe('slugifyName / validateName', () => {
  it('slugifies to the allowed alphabet', () => {
    expect(slugifyName('  Order Update! (v2) ')).toBe('order_update_v2');
    expect(slugifyName('Café déjà vu')).toBe('cafe_deja_vu');
    expect(slugifyName('___')).toBe('');
    expect(slugifyName('a'.repeat(600))).toHaveLength(512);
    expect(validateName(slugifyName('Hello World'))).toBeNull();
  });

  it('flags bad names', () => {
    expect(validateName('')).toMatch(/required/);
    expect(validateName('Has Caps')).toMatch(/lowercase/);
    expect(validateName('a'.repeat(513))).toMatch(/512/);
    expect(validateName('ok_name_1')).toBeNull();
  });
});

describe('validateDraft basics', () => {
  it('accepts a minimal draft', () => {
    expect(validateDraft(valid())).toEqual({});
    expect(canSubmit(valid())).toBe(true);
  });

  it('requires name, language and body', () => {
    const e = validateDraft(valid({ name: '', language: '', body: ' ' }));
    expect(Object.keys(e).sort()).toEqual(['body', 'language', 'name']);
    expect(validateDraft(valid({ language: 'xx_YY' })).language).toMatch(/not supported/);
    expect(canSubmit(valid({ name: '' }))).toBe(false);
  });

  it('caps body at 1024 and footer at 60, and bars footer variables', () => {
    expect(validateDraft(valid({ body: 'a'.repeat(1025) })).body).toMatch(/1024/);
    expect(validateDraft(valid({ body: 'a'.repeat(1024) })).body).toBeUndefined();
    expect(validateDraft(valid({ footer: 'a'.repeat(61) })).footer).toMatch(/60/);
    expect(validateDraft(valid({ footer: 'a'.repeat(60) })).footer).toBeUndefined();
    expect(validateDraft(valid({ footer: 'hi {{1}}' })).footer).toMatch(/variables/);
  });
});

describe('variables', () => {
  it('needs samples for every numbered variable', () => {
    const d = valid({ body: 'Hi {{1}}, order {{2}} shipped' });
    expect(Object.keys(validateDraft(d)).sort()).toEqual(['samples.1', 'samples.2']);
    expect(validateDraft({ ...d, samples: { '1': 'Ann', '2': '4821' } })).toEqual({});
  });

  it('rejects gaps and bad syntax', () => {
    expect(validateDraft(valid({ body: 'Hi {{2}} there', samples: { '2': 'a' } })).body).toMatch(/without gaps/);
    expect(validateDraft(valid({ body: 'Hi {{1} there' })).body).toMatch(/must look like/);
    expect(validateDraft(valid({ body: 'Hi {{Bad Name}} there' })).body).toMatch(/must look like/);
  });

  it('rejects a body that starts or ends with a variable', () => {
    const samples = { '1': 'Ann' };
    expect(validateDraft(valid({ body: '{{1}} hello', samples })).body).toMatch(/start/);
    expect(validateDraft(valid({ body: 'hello {{1}}', samples })).body).toMatch(/end/);
    expect(validateDraft(valid({ body: 'hello {{1}}  ', samples })).body).toMatch(/end/);
    expect(validateDraft(valid({ body: 'a {{1}} b', samples }))).toEqual({});
  });

  it('validates named variables', () => {
    const base = valid({ variableType: 'name', samples: { first_name: 'Ann' } });
    expect(validateDraft({ ...base, body: 'Hi {{first_name}}, welcome' })).toEqual({});
    expect(validateDraft({ ...base, body: 'Hi {{First}}, welcome' }).body).toMatch(/must look like/);
    expect(validateDraft({ ...base, body: 'Hi {{1first}}, welcome' }).body).toMatch(/must look like/);
    expect(validateDraft({ ...base, body: 'Hi {{first_name}} {{first_name}} bye' }).body).toMatch(/only be used once/);
  });

  it('does not mix numbered and named', () => {
    expect(validateDraft(valid({ variableType: 'name', body: 'a {{1}} b', samples: { '1': 'x' } })).body).toMatch(/Numbered/);
    expect(validateDraft(valid({ variableType: 'number', body: 'a {{n}} b', samples: { n: 'x' } })).body).toMatch(/Named/);
    expect(validateDraft(valid({ variableType: 'number', body: 'a {{1}} {{n}} b' })).body).toMatch(/mixed/);
  });

  it('rejects samples that look like a phone number or email, and commas for numbered', () => {
    expect(sampleProblem('+1 555 123 4567', 'x')).toMatch(/phone/);
    expect(sampleProblem('5551234567', 'x')).toMatch(/phone/);
    expect(sampleProblem('ann@example.com', 'x')).toMatch(/email/);
    expect(sampleProblem('order 12', 'x')).toBeNull();
    expect(sampleProblem('', 'x')).toMatch(/Add an example/);
    const d = valid({ body: 'a {{1}} b' });
    expect(validateDraft({ ...d, samples: { '1': 'ann@example.com' } })['samples.1']).toMatch(/email/);
    expect(validateDraft({ ...d, samples: { '1': 'a, b' } })['samples.1']).toMatch(/commas/);
    const named = valid({ variableType: 'name', body: 'a {{n}} b', samples: { n: 'a, b' } });
    expect(validateDraft(named)['samples.n']).toBeUndefined();
  });
});

describe('header', () => {
  const text = (t: string, samples: Record<string, string> = {}) =>
    valid({ header: { type: 'text', text: t, mediaSample: '' }, samples });

  it('limits text to 60 and one variable', () => {
    expect(validateDraft(text(''))['header.text']).toMatch(/required/);
    expect(validateDraft(text('a'.repeat(61)))['header.text']).toMatch(/60/);
    expect(validateDraft(text('a'.repeat(60)))).toEqual({});
    expect(validateDraft(text('{{1}} and {{2}}', { 'header.1': 'a', 'header.2': 'b' }))['header.text']).toMatch(/at most one/);
  });

  it('needs a sample for the header variable', () => {
    expect(validateDraft(text('Hi {{1}}'))['samples.header.1']).toMatch(/Add an example/);
    expect(validateDraft(text('Hi {{1}}', { 'header.1': 'Ann' }))).toEqual({});
  });

  it('supports a named header variable', () => {
    const d = valid({ variableType: 'name', header: { type: 'text', text: 'Hi {{who}}', mediaSample: '' }, samples: { 'header.who': 'Ann' } });
    expect(validateDraft(d)).toEqual({});
    expect(validateDraft({ ...d, header: { ...d.header, text: 'Hi {{1}}' } })['header.text']).toMatch(/named/);
  });

  it('allows no variable in a media header and needs a sample file', () => {
    for (const type of ['image', 'video', 'document'] as const) {
      expect(validateDraft(valid({ header: { type, text: '{{1}}', mediaSample: '' } }))['header.mediaSample']).toMatch(/sample file/);
      expect(validateDraft(valid({ header: { type, text: '{{1}}', mediaSample: 'ftp://x' } }))['header.mediaSample']).toMatch(/http/);
      expect(validateDraft(valid({ header: { type, text: '{{1}}', mediaSample: 'https://e.com/a' } }))).toEqual({});
      expect(validateDraft(valid({ header: { type, text: '', mediaSample: '/files/a.png' } }))).toEqual({});
    }
  });

  it('location needs nothing', () => {
    expect(validateDraft(valid({ header: { type: 'location', text: '', mediaSample: '' } }))).toEqual({});
  });
});

describe('buttons', () => {
  const withButtons = (buttons: WizardButton[]) => validateDraft(valid({ buttons }));

  it('allows up to 10 in total', () => {
    expect(withButtons(Array.from({ length: 10 }, quick))).toEqual({});
    expect(withButtons(Array.from({ length: 11 }, quick)).buttons).toMatch(/10/);
  });

  it('limits url, phone and copy code', () => {
    expect(withButtons([url(), url(), url()]).buttons).toMatch(/2 website/);
    expect(withButtons([phone(), phone()]).buttons).toMatch(/one phone/);
    const copy = () => btn('COPY_CODE', { codeExample: 'SAVE20' });
    expect(withButtons([copy(), copy()]).buttons).toMatch(/one copy code/);
    expect(withButtons([url(), url(), phone(), copy()])).toEqual({});
  });

  it('keeps quick replies and call-to-action grouped', () => {
    expect(withButtons([quick(), quick(), url()])).toEqual({});
    expect(withButtons([url(), phone(), quick()])).toEqual({});
    expect(withButtons([quick(), url(), quick()]).buttons).toMatch(/together/);
    expect(withButtons([url(), quick(), phone()]).buttons).toMatch(/together/);
  });

  it('limits button text to 25 and requires it', () => {
    expect(withButtons([quick()])).toEqual({});
    expect(withButtons([btn('QUICK_REPLY', { text: '' })])['buttons.0.text']).toMatch(/required/);
    expect(withButtons([btn('QUICK_REPLY', { text: 'a'.repeat(26) })])['buttons.0.text']).toMatch(/25/);
    expect(withButtons([btn('QUICK_REPLY', { text: 'a'.repeat(25) })])).toEqual({});
  });

  it('validates URL buttons, with the variable only at the end', () => {
    expect(withButtons([url({ url: 'example.com' })])['buttons.0.url']).toMatch(/http/);
    expect(withButtons([url({ url: 'https://e.com/{{1}}/x' })])['buttons.0.url']).toMatch(/very end/);
    expect(withButtons([url({ url: 'https://e.com/{{2}}' })])['buttons.0.url']).toMatch(/very end/);
    expect(withButtons([url({ url: 'https://e.com/{{1}}{{1}}' })])['buttons.0.url']).toMatch(/very end/);
    expect(withButtons([url({ url: 'https://e.com/{{1}}' })])['buttons.0.urlExample']).toMatch(/example/);
    expect(withButtons([url({ url: 'https://e.com/{{1}}', urlExample: 'https://other.com/5' })])['buttons.0.urlExample']).toMatch(/start with/);
    expect(withButtons([url({ url: 'https://e.com/{{1}}', urlExample: 'https://e.com/' })])['buttons.0.urlExample']).toMatch(/start with/);
    expect(withButtons([url({ url: 'https://e.com/{{1}}', urlExample: 'https://e.com/5' })])).toEqual({});
  });

  it('validates phone and copy code buttons', () => {
    expect(withButtons([btn('PHONE_NUMBER', { phoneNumber: '5551234' })])['buttons.0.phoneNumber']).toMatch(/international/);
    expect(withButtons([btn('PHONE_NUMBER', { phoneNumber: '+1 (555) 123-4567' })])).toEqual({});
    expect(withButtons([btn('COPY_CODE')])['buttons.0.codeExample']).toMatch(/Add an example/);
    expect(withButtons([btn('COPY_CODE', { codeExample: 'a'.repeat(21) })])['buttons.0.codeExample']).toMatch(/20/);
    expect(withButtons([btn('COPY_CODE', { codeExample: 'no spaces' })])['buttons.0.codeExample']).toBeDefined();
  });
});

describe('ttl', () => {
  it('is Utility only and within 30 seconds to 30 days', () => {
    expect(validateDraft(valid({ category: 'MARKETING', ttl: 3600 })).ttl).toMatch(/Utility/);
    expect(validateDraft(valid({ category: 'UTILITY', ttl: 3600 }))).toEqual({});
    expect(validateDraft(valid({ category: 'UTILITY', ttl: 29 })).ttl).toMatch(/between/);
    expect(validateDraft(valid({ category: 'UTILITY', ttl: 12 * 3600 + 1 })).ttl).toMatch(/between/);
    expect(validateDraft(valid({ category: 'UTILITY', ttl: null }))).toEqual({});
  });
});

describe('stepOfField', () => {
  it('maps fields to wizard steps', () => {
    expect(stepOfField('name')).toBe('setup');
    expect(stepOfField('language')).toBe('setup');
    expect(stepOfField('buttons.0.text')).toBe('content');
  });

  it('puts category on the type step', () => {
    expect(stepOfField('category')).toBe('type');
  });
});
