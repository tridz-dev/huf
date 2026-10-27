import { describe, expect, it } from 'vitest';
import { TEMPLATE_KINDS, isSelectableKind, kindById } from './catalogue';
import { isKnownLocale, localeLabel, TEMPLATE_LOCALES } from './locales';
import { emptyDraft } from './draft';
import { buildWizardPreview } from './preview';

describe('catalogue', () => {
  it('offers Marketing and Utility, disables Authentication, and flags the rest as coming soon', () => {
    const byId = (id: string) => kindById(id)!;
    expect(byId('marketing_default')).toMatchObject({ category: 'MARKETING', availability: 'available' });
    expect(byId('utility_default')).toMatchObject({ category: 'UTILITY', availability: 'available' });
    expect(byId('authentication').availability).toBe('disabled');
    expect(byId('authentication').disabledReason).toBeTruthy();
    for (const id of ['catalogue', 'flows', 'calling']) expect(byId(id).availability).toBe('comingSoon');
    expect(TEMPLATE_KINDS.filter(isSelectableKind).map((k) => k.id)).toEqual(['marketing_default', 'utility_default']);
  });

  it('describes every kind', () => {
    for (const k of TEMPLATE_KINDS) {
      expect(k.description).toBeTruthy();
      expect(k.goodFor.length).toBeGreaterThan(0);
      expect(k.customisable.length).toBeGreaterThan(0);
      expect(k.sample.body).toBeTruthy();
    }
  });
});

describe('locales', () => {
  it('covers the common Meta locales with labels', () => {
    for (const c of ['en_US', 'en_GB', 'ar', 'pt_BR', 'hi', 'es', 'fr', 'de', 'id', 'tr', 'ru', 'zh_CN']) expect(isKnownLocale(c)).toBe(true);
    expect(localeLabel('pt_BR')).toBe('Portuguese (Brazil)');
    expect(localeLabel('zz')).toBe('zz');
    expect(isKnownLocale('xx')).toBe(false);
    expect(new Set(TEMPLATE_LOCALES.map((l) => l.code)).size).toBe(TEMPLATE_LOCALES.length);
  });
});

describe('buildWizardPreview', () => {
  it('fills samples, formats the body and keeps unfilled variables visible', () => {
    const d = {
      ...emptyDraft(),
      header: { type: 'text' as const, text: 'Hi {{1}}', mediaSample: '' },
      body: 'Order *{{1}}* for {{2}} done',
      footer: ' bye ',
      samples: { 'header.1': 'Ann', '1': '4821' },
    };
    const p = buildWizardPreview(d);
    expect(p.header).toEqual({ kind: 'text', segments: [{ text: 'Hi Ann' }] });
    expect(p.body).toEqual([{ text: 'Order ' }, { text: '4821', bold: true }, { text: ' for {{2}} done' }]);
    expect(p.footer).toBe('bye');
  });

  it('previews media headers and default button text', () => {
    const p = buildWizardPreview({
      ...emptyDraft(),
      header: { type: 'video', text: '', mediaSample: ' https://e.com/v.mp4 ' },
      buttons: [{ id: '1', type: 'URL', text: ' ', url: '', urlExample: '', phoneNumber: '', codeExample: '' }],
    });
    expect(p.header).toEqual({ kind: 'media', media: 'video', url: 'https://e.com/v.mp4' });
    expect(p.buttons).toEqual([{ type: 'URL', text: 'Button' }]);
    expect(buildWizardPreview(emptyDraft()).header).toBeNull();
  });
});
