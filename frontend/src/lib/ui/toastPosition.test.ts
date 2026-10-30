import { describe, expect, it } from 'vitest';
import { toastPosition } from './toastPosition';

describe('toastPosition', () => {
  it('moves toasts to the bottom right on a flow canvas, clear of the bottom-left minimap', () => {
    expect(toastPosition('/flows/abc123', false)).toBe('bottom-right');
    expect(toastPosition('/huf/flows/abc123', false)).toBe('bottom-right');
  });
  it('keeps bottom centre elsewhere and the top on a phone', () => {
    expect(toastPosition('/flows', false)).toBe('bottom-center');
    expect(toastPosition('/agents/x', false)).toBe('bottom-center');
    expect(toastPosition('/flows/abc123', true)).toBe('top-center');
  });
});
