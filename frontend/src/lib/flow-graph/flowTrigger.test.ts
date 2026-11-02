import { describe, expect, it } from 'vitest';
import { EVENT_WORD, DOC_EVENTS, filterDoctypes } from './flowTrigger';

const row = (name: string, label = name, module = 'Desk') => ({ name, label, module });
const catalog = [row('ToDo', 'To-do'), row('Customer', 'Customer', 'Selling'), row('Sales Order', 'Sales Order', 'Selling'), row('Contact', 'Contact', 'Contacts'), row('Uiv Wp7 Doc', 'Uiv Wp7 Doc', 'Custom')];

describe('filterDoctypes (B14)', () => {
  it('searching todo finds the To-do and nothing unrelated', () => {
    expect(filterDoctypes(catalog, 'todo').map((d) => d.name)).toEqual(['ToDo']);
    expect(filterDoctypes(catalog, 'to-do').map((d) => d.name)).toEqual(['ToDo']);
  });
  it('puts names that start with the text first, then names that contain it', () => {
    expect(filterDoctypes(catalog, 'con').map((d) => d.name)).toEqual(['Contact']);
    expect(filterDoctypes(catalog, 'ord').map((d) => d.name)).toEqual(['Sales Order']);
  });
  it('matches the module as a last resort and an empty search shows everything', () => {
    expect(filterDoctypes(catalog, 'selling').map((d) => d.name)).toEqual(['Customer', 'Sales Order']);
    expect(filterDoctypes(catalog, '  ')).toHaveLength(5);
    expect(filterDoctypes(catalog, 'zzz')).toEqual([]);
  });
});

describe('event words', () => {
  it('names every event in plain words', () => {
    for (const e of DOC_EVENTS) expect(EVENT_WORD[e]).toMatch(/^[a-z]+$/);
  });
});
