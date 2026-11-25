import { describe, expect, it } from 'vitest';
import { CircleDashed, MessageSquare, Puzzle } from 'lucide-react';
import { paletteIcon } from './nodeIcons';

describe('paletteIcon for app steps', () => {
  it('reads a lucide name in any spelling and falls back to Puzzle for an unknown one', () => {
    expect(paletteIcon('MessageSquare')).toBe(MessageSquare);
    expect(paletteIcon('message-square')).toBe(MessageSquare);
    expect(paletteIcon('puzzle')).toBe(Puzzle);
    expect(paletteIcon('no-such-icon')).toBe(Puzzle);
    expect(paletteIcon(undefined)).toBe(CircleDashed);
  });
});
