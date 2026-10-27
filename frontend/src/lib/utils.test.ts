import { describe, expect, it } from 'vitest';
import { cn } from './utils';

describe('cn', () => {
  it.each(['display', 'title', 'subtitle', 'micro', 'body-text', 'ui-text', 'meta', 'eyebrow'])(
    'keeps text-%s and a text colour in both orders',
    (size) => {
      expect(cn(`text-${size}`, 'text-steel').split(' ').sort()).toEqual([`text-${size}`, 'text-steel'].sort());
      expect(cn('text-steel', `text-${size}`).split(' ').sort()).toEqual([`text-${size}`, 'text-steel'].sort());
    },
  );

  it('still lets a later font size override an earlier one', () => {
    expect(cn('text-micro', 'text-sm')).toBe('text-sm');
    expect(cn('text-sm', 'text-micro')).toBe('text-micro');
  });

  it('still lets a later colour override an earlier colour', () => {
    expect(cn('text-steel', 'text-ink')).toBe('text-ink');
  });
});
