import { describe, expect, it } from 'vitest';
import { kindById, isSelectableKind } from './catalogue';
import { addCard, addCardButton, moveCard, removeCard, removeCardButton, startCarousel, updateCard } from './cards';
import { emptyDraft } from './draft';
import { fromTemplateDetail, toCreatePayload } from './payload';
import { validateDraft, variableAtEdge } from './rules';
import type { TemplateDetail } from '@/services/whatsappApi';

let n = 0;
const id = () => `c${(n += 1)}`;

function valid() {
  let d = startCarousel({ ...emptyDraft('MARKETING'), name: 'spring_cards', body: 'Hi, see our picks' }, id);
  d = updateCard(d, 0, { mediaSample: 'https://x.example/a.png', body: 'Card one {{1}} now', samples: ['A'] });
  d = updateCard(d, 1, { mediaSample: 'https://x.example/b.png', body: 'Card two' });
  d = addCardButton(d, 'URL', 'u');
  d.cards.forEach((c, i) => {
    c.buttons[0].text = `Reply ${i}`;
    c.buttons[1].text = `Go ${i}`;
    c.buttons[1].url = 'https://x.example/';
  });
  return d;
}

describe('carousel kind', () => {
  it('is an available marketing kind', () => {
    const k = kindById('marketing_carousel')!;
    expect(isSelectableKind(k)).toBe(true);
    expect(k.carousel).toBe(true);
    expect(k.category).toBe('MARKETING');
  });
});

describe('card list state', () => {
  it('starts with 2 cards, adds up to 10, removes, reorders', () => {
    let d = startCarousel(emptyDraft(), id);
    expect(d.cards).toHaveLength(2);
    for (let i = 0; i < 12; i++) d = addCard(d, id());
    expect(d.cards).toHaveLength(10);
    const first = d.cards[0].id;
    d = moveCard(d, 0, 1);
    expect(d.cards[1].id).toBe(first);
    d = removeCard(d, 1);
    expect(d.cards).toHaveLength(9);
  });
  it('keeps button sets identical across cards', () => {
    let d = startCarousel(emptyDraft(), id);
    d = addCardButton(d, 'URL', 'u');
    expect(d.cards.map((c) => c.buttons.length)).toEqual([2, 2]);
    d = addCardButton(d, 'QUICK_REPLY', 'q');
    expect(d.cards[0].buttons).toHaveLength(2);
    d = removeCardButton(d, 0);
    expect(d.cards.map((c) => c.buttons[0].type)).toEqual(['URL', 'URL']);
    expect(addCard(d, id()).cards[2].buttons[0].type).toBe('URL');
  });
});

describe('carousel validation', () => {
  it('accepts a complete carousel', () => {
    expect(validateDraft(valid())).toEqual({});
  });
  it('flags card count, media, body, sample, buttons and mismatch', () => {
    let d = valid();
    expect(validateDraft({ ...d, cards: d.cards.slice(0, 1) }).cards).toMatch(/2 to 10/);
    d = updateCard(d, 0, { mediaSample: '' });
    d = updateCard(d, 1, { body: '' });
    d = updateCard(d, 0, { samples: [''] });
    const e = validateDraft(d);
    expect(e['cards.0.mediaSample']).toBeTruthy();
    expect(e['cards.1.body']).toBeTruthy();
    expect(e['cards.0.samples.1']).toBeTruthy();
    const m = valid();
    m.cards[1] = { ...m.cards[1], buttons: [m.cards[1].buttons[0]] };
    expect(validateDraft(m).cards).toMatch(/same buttons/);
  });
  it('rejects non-marketing carousels', () => {
    expect(validateDraft({ ...valid(), category: 'UTILITY' }).category).toBeTruthy();
  });
  it('leaves non-carousel validation alone', () => {
    expect(validateDraft({ ...emptyDraft(), name: 'x', body: 'Hello there' })).toEqual({});
  });
});

describe('carousel payload', () => {
  it('sends cards and no header/footer/buttons', () => {
    const p = toCreatePayload(valid());
    expect(p.header_type).toBeUndefined();
    expect(p.footer).toBeUndefined();
    expect(p.buttons).toBeUndefined();
    expect(p.cards).toHaveLength(2);
    expect(p.cards![0]).toMatchObject({ header_type: 'IMAGE', sample: 'https://x.example/a.png', sample_values: 'A' });
    expect(p.cards![0].buttons.map((b) => b.type)).toEqual(['QUICK_REPLY', 'URL']);
  });
  it('restores a draft from template detail', () => {
    const detail = {
      template_name: 't', language_code: 'en_US', category: 'MARKETING', parameter_format: 'POSITIONAL',
      components: {
        header: null, body: { text: 'Hi all', sample_values: [] }, footer: null, buttons: [],
        carousel: [
          { header_type: 'VIDEO', header_example: '4::handle', body: 'A {{1}} b', body_vars: ['1'], sample_values: ['x'],
            buttons: [{ type: 'QUICK_REPLY', dynamic: false, text: 'Hi' }] },
          { header_type: 'IMAGE', header_example: 'https://x.example/i.png', body: 'B', body_vars: [], buttons: [{ type: 'QUICK_REPLY', dynamic: false, text: 'Yo' }] },
        ],
      },
    } as unknown as TemplateDetail;
    const d = fromTemplateDetail(detail);
    expect(d.carousel).toBe(true);
    expect(d.cards[0]).toMatchObject({ headerType: 'video', mediaSample: '', samples: ['x'] });
    expect(d.cards[1].mediaSample).toBe('https://x.example/i.png');
    expect(d.cards[0].buttons[0].text).toBe('Hi');
  });
});

describe('variables at the edge (Meta 100/2388299)', () => {
  it('detects start and end variables', () => {
    expect(variableAtEdge('{{1}} hi')).toBe(true);
    expect(variableAtEdge('hi {{1}}  ')).toBe(true);
    expect(variableAtEdge('hi {{1}} there')).toBe(false);
  });
  it('rejects them in the carousel body and in card bodies', () => {
    const d = valid();
    expect(validateDraft(d).body).toBeUndefined();
    expect(validateDraft({ ...d, body: 'Hi {{1}}', samples: { '1': 'A' } }).body).toMatch(/start or end/);
    const c = updateCard(d, 1, { body: '{{1}} deal', samples: ['A'] });
    expect(validateDraft(c)['cards.1.body']).toMatch(/start or end/);
  });
});
