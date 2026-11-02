import { describe, expect, it } from 'vitest';
import { fieldFromSchema, labelFromKey, normalizePasted, PRESET_FIELDS } from './toolPresetFields';

describe('pasted links', () => {
  it('a sheet link gives the id', () => {
    expect(normalizePasted('google', 'https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUv/edit#gid=0')).toBe('1AbCdEfGhIjKlMnOpQrStUv');
  });
  it('a drive file link gives the id', () => {
    expect(normalizePasted('google', 'https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQrStUv/view?usp=sharing')).toBe('1AbCdEfGhIjKlMnOpQrStUv');
    expect(normalizePasted('google', 'https://drive.google.com/open?id=1AbCdEfGhIjKlMnOpQrStUv')).toBe('1AbCdEfGhIjKlMnOpQrStUv');
  });
  it('an id, other text and data are left alone', () => {
    expect(normalizePasted('google', '1AbCdEfGhIjKlMnOpQrStUv')).toBe('1AbCdEfGhIjKlMnOpQrStUv');
    expect(normalizePasted('google', 'https://example.com/page')).toBe('https://example.com/page');
    expect(normalizePasted('google', { $from: 'input.sheet' })).toEqual({ $from: 'input.sheet' });
  });
  it('a Slack message link gives the thread time', () => {
    expect(normalizePasted('slack_thread', 'https://tridz.slack.com/archives/C0CCDGTDBHR/p1712345678000100')).toBe('1712345678.000100');
  });
});

describe('labels', () => {
  it('turns a key into words', () => {
    expect(labelFromKey('customer_name')).toBe('Customer name');
    expect(labelFromKey('file_id')).toBe('File ID');
    expect(labelFromKey('callbackUrl')).toBe('Callback address');
  });
  it('picks a box from the schema', () => {
    expect(fieldFromSchema('limit', { type: 'integer' }, false).kind).toBe('number');
    expect(fieldFromSchema('notify', { type: 'boolean' }, false).kind).toBe('yesno');
    expect(fieldFromSchema('rows', { type: 'array' }, true)).toMatchObject({ kind: 'json', optional: false });
    expect(fieldFromSchema('mode', { type: 'string', enum: ['a', 'b'] }, true).hint).toContain('One of: a, b');
  });
});

describe('presets', () => {
  it('no preset talks about ids, tools or syntax', () => {
    const text = Object.values(PRESET_FIELDS).flat().map((f) => `${f.label} ${f.placeholder ?? ''} ${f.hint ?? ''}`).join('\n');
    expect(text).not.toMatch(/\bMCP\b|\bbot\b|literal|\$from|spreadsheet_id/i);
  });
  it('required fields come before optional ones', () => {
    for (const fields of Object.values(PRESET_FIELDS)) {
      const firstOptional = fields.findIndex((f) => f.optional);
      if (firstOptional >= 0) expect(fields.slice(firstOptional).every((f) => f.optional)).toBe(true);
    }
  });
});
