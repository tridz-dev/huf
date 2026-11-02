import { describe, it, expect } from 'vitest';
import { paletteFilter } from './paletteFilter';

describe('palette search', () => {
  it('finds a step by its name or by a word of its description, and nothing by scattered letters', () => {
    expect(paletteFilter('add Send email', 'email', ['Send a message from Gmail'])).toBeGreaterThan(0);
    expect(paletteFilter('add Web request', 'answer', ['Call a web address and use the answer.'])).toBeGreaterThan(0);
    // cmdk's default matched "target" inside "Call a web address and use the answer" letter by letter
    expect(paletteFilter('add Web request', 'target', ['Call a web address and use the answer.'])).toBe(0);
  });
  it('needs every word, ranks a title match above a description match, and shows everything for an empty search', () => {
    expect(paletteFilter('add Send email', 'send slack', [])).toBe(0);
    expect(paletteFilter('add Send email', 'send', [])).toBeGreaterThan(paletteFilter('add Run agent', 'send', ['Give an agent a task and send it']));
    expect(paletteFilter('anything', '  ', [])).toBe(1);
  });
});
