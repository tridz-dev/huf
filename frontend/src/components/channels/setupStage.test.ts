import { describe, expect, it } from 'vitest';
import { stageLabel } from './setupStage';

describe('stageLabel', () => {
  it('uses plain words, never the raw stage code', () => {
    expect(stageLabel('connected_unverified')).toBe('Connected, not tested yet');
    expect(stageLabel('live_unrouted')).not.toMatch(/_/);
    expect(stageLabel('something_new')).toBe('Setting up');
    expect(stageLabel(null)).toBe('Setting up');
  });
});
