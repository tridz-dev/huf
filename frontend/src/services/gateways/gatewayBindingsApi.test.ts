import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/frappe-sdk', () => ({ call: { post: vi.fn() } }));
import {
  bindingFormSchema,
  describeRule,
  moveItem,
  sortByPriority,
} from './gatewayBindingsApi';

const base = { match_type: 'Room or channel', match_value: 'C1', target_type: 'Agent', agent: 'Support' } as const;

describe('bindingFormSchema', () => {
  it('accepts a valid channel rule', () => {
    expect(bindingFormSchema.safeParse(base).success).toBe(true);
  });
  it('requires a value unless any conversation', () => {
    expect(bindingFormSchema.safeParse({ ...base, match_value: ' ' }).success).toBe(false);
    expect(bindingFormSchema.safeParse({ ...base, match_type: 'Any conversation', match_value: '' }).success).toBe(true);
  });
  it('rejects a value for any conversation', () => {
    expect(bindingFormSchema.safeParse({ ...base, match_type: 'Any conversation' }).success).toBe(false);
  });
  it('requires the matching target', () => {
    expect(bindingFormSchema.safeParse({ ...base, agent: '' }).success).toBe(false);
    expect(bindingFormSchema.safeParse({ ...base, target_type: 'Flow' }).success).toBe(false);
    expect(bindingFormSchema.safeParse({ ...base, target_type: 'Flow', flow: 'F1' }).success).toBe(true);
  });
});

describe('ordering helpers', () => {
  it('sorts by priority then name', () => {
    const out = sortByPriority([
      { name: 'b', priority: 2 },
      { name: 'z', priority: 1 },
      { name: 'a', priority: 2 },
    ]);
    expect(out.map((r) => r.name)).toEqual(['z', 'a', 'b']);
  });
  it('moves and clamps without mutating', () => {
    const src = ['a', 'b', 'c'];
    expect(moveItem(src, 2, -1)).toEqual(['a', 'c', 'b']);
    expect(moveItem(src, 0, -1)).toEqual(['a', 'b', 'c']);
    expect(moveItem(src, 1, 5)).toEqual(['a', 'c', 'b']);
    expect(src).toEqual(['a', 'b', 'c']);
  });
});

describe('describeRule', () => {
  it('uses plain wording and labels', () => {
    expect(describeRule(base, () => '#support')).toBe(
      'When a message arrives in #support, send it to Support agent'
    );
  });
});
