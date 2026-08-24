// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { estimateWordTimings } from './MeetingRecordingPlayer';

describe('estimateWordTimings', () => {
  it('returns an empty array for empty string input', () => {
    expect(estimateWordTimings('', 10)).toEqual([]);
  });

  it('returns one entry with startSeconds 0 for a single word with a positive duration', () => {
    const result = estimateWordTimings('hello', 5);
    expect(result).toEqual([{ word: 'hello', startSeconds: 0 }]);
  });

  it('evenly spaces N words across durationSeconds', () => {
    const result = estimateWordTimings('one two three four', 40);
    expect(result.map((t) => t.startSeconds)).toEqual([0, 10, 20, 30]);
    expect(result.map((t) => t.word)).toEqual(['one', 'two', 'three', 'four']);
  });

  it('degrades gracefully with durationSeconds of 0, returning all words at startSeconds 0', () => {
    const result = estimateWordTimings('one two three', 0);
    expect(result).toEqual([
      { word: 'one', startSeconds: 0 },
      { word: 'two', startSeconds: 0 },
      { word: 'three', startSeconds: 0 },
    ]);
  });

  it('does not produce empty-string words from extra/leading/trailing whitespace', () => {
    const result = estimateWordTimings('  hello   world  ', 10);
    expect(result.map((t) => t.word)).toEqual(['hello', 'world']);
    expect(result.every((t) => t.word.length > 0)).toBe(true);
  });
});
