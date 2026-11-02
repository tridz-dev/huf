import { describe, expect, it } from 'vitest';
import { SOURCE_LABEL, ageText, durationText, parseSampleInput, testButtonHint, testButtonLabel } from './testModel';

const base = { simulated: false, calls_ai: false, approval: false, trigger: false };

describe('Test tab words', () => {
  it('names the button after what it does', () => {
    expect(testButtonLabel({ simulated: false })).toBe('Test step');
    expect(testButtonLabel({ simulated: true })).toBe('Test (simulated)');
  });

  it('explains in one line whether anything is sent', () => {
    expect(testButtonHint({ ...base, simulated: true })).toContain('Nothing is sent');
    expect(testButtonHint({ ...base, approval: true })).toContain('card the approver would see');
    expect(testButtonHint({ ...base, calls_ai: true })).toContain('AI model');
    expect(testButtonHint(base)).toContain('Nothing is sent or changed');
  });

  it('says where a sample came from', () => {
    expect(SOURCE_LABEL.pinned).toBe('From pinned sample');
    expect(SOURCE_LABEL.last_run).toBe('From last run');
    expect(SOURCE_LABEL.trigger_sample).toBe('From trigger sample');
    expect(SOURCE_LABEL.edited).toBe('Edited sample');
  });

  it('tells time in words', () => {
    const now = Date.parse('2026-10-30T12:00:00Z');
    expect(ageText('2026-10-30T11:59:50Z', now)).toBe('just now');
    expect(ageText('2026-10-30T11:55:00Z', now)).toBe('5 min ago');
    expect(ageText('2026-10-30T10:00:00Z', now)).toBe('2 hours ago');
    expect(ageText('2026-10-29T12:00:00Z', now)).toBe('yesterday');
    expect(ageText('2026-10-27T12:00:00Z', now)).toBe('3 days ago');
    expect(ageText(undefined, now)).toBe('');
    expect(durationText(120)).toBe('120 ms');
    expect(durationText(2400)).toBe('2.4 s');
    expect(durationText(25000)).toBe('25 s');
  });

  it('accepts a sample only when it is a JSON object', () => {
    expect(parseSampleInput('{"input": {"a": 1}}')).toEqual({ ok: true, value: { input: { a: 1 } } });
    expect(parseSampleInput('[1]').ok).toBe(false);
    expect(parseSampleInput('{oops').ok).toBe(false);
  });
});
