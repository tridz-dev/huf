import { describe, expect, it } from 'vitest';
import { isArrowKey, nextStepFor } from './keyNav';

const at = (id: string, x: number, y: number) => ({ id, position: { x, y } });
const steps = [at('t', 250, 100), at('c', 250, 250), at('yes', 105, 400), at('no', 395, 400), at('end', 250, 550)];
const links = [
  { source: 't', target: 'c' },
  { source: 'c', target: 'no' },
  { source: 'c', target: 'yes' },
  { source: 'yes', target: 'end' },
  { source: 'no', target: 'end' },
];

describe('nextStepFor', () => {
  it('goes down to the step a connection leads to, the leftmost branch first', () => {
    expect(nextStepFor('ArrowDown', 't', steps, links)).toBe('c');
    expect(nextStepFor('ArrowDown', 'c', steps, links)).toBe('yes');
    expect(nextStepFor('ArrowDown', 'end', steps, links)).toBeNull();
  });
  it('goes up to the step that leads here', () => {
    expect(nextStepFor('ArrowUp', 'end', steps, links)).toBe('yes');
    expect(nextStepFor('ArrowUp', 't', steps, links)).toBeNull();
  });
  it('moves sideways between neighbours on one row', () => {
    expect(nextStepFor('ArrowRight', 'yes', steps, links)).toBe('no');
    expect(nextStepFor('ArrowLeft', 'no', steps, links)).toBe('yes');
    expect(nextStepFor('ArrowLeft', 'yes', steps, links)).toBeNull();
    expect(nextStepFor('ArrowRight', 'c', steps, links)).toBeNull();
  });
  it('knows an unknown step and recognises arrow keys', () => {
    expect(nextStepFor('ArrowDown', 'zzz', steps, links)).toBeNull();
    expect(isArrowKey('ArrowUp')).toBe(true);
    expect(isArrowKey('Enter')).toBe(false);
  });
});
