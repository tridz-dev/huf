import { describe, expect, it } from 'vitest';
import { presetToReasoning, presetToTemperature, reasoningToPreset, temperatureToPreset } from './presets';

describe('creativity presets', () => {
  it('maps presets to temperatures', () => {
    expect(presetToTemperature('precise')).toBe(0.2);
    expect(presetToTemperature('balanced')).toBe(0.7);
    expect(presetToTemperature('creative')).toBe(1);
  });
  it('maps temperatures back, tolerating float noise', () => {
    expect(temperatureToPreset(0.2)).toBe('precise');
    expect(temperatureToPreset(0.7000000001)).toBe('balanced');
    expect(temperatureToPreset(1)).toBe('creative');
  });
  it('treats anything else as custom, never rewriting it', () => {
    expect(temperatureToPreset(0.5)).toBe('custom');
    expect(temperatureToPreset(1.6)).toBe('custom');
    expect(temperatureToPreset(undefined)).toBe('custom');
    expect(temperatureToPreset(NaN)).toBe('custom');
  });
  it('round-trips', () => {
    for (const p of ['precise', 'balanced', 'creative'] as const) expect(temperatureToPreset(presetToTemperature(p))).toBe(p);
  });
});

describe('thinking presets', () => {
  it('round-trips named presets', () => {
    for (const p of ['off', 'auto', 'light', 'deep'] as const) {
      const r = presetToReasoning(p);
      expect(reasoningToPreset(r.reasoning_mode, r.reasoning_effort)).toBe(p);
    }
  });
  it('defaults missing values to Auto', () => {
    expect(reasoningToPreset(undefined, undefined)).toBe('auto');
  });
  it('Off ignores effort', () => {
    expect(reasoningToPreset('Off', 'High')).toBe('off');
  });
  it('unmatched combinations are custom', () => {
    expect(reasoningToPreset('On', 'Medium')).toBe('custom');
    expect(reasoningToPreset('Auto', 'High')).toBe('custom');
  });
});
