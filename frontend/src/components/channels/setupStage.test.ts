import { describe, expect, it } from 'vitest';
import { stageLabel } from './setupStage';

describe('stageLabel', () => {
  it('uses plain words, never the raw stage code', () => {
    expect(stageLabel('connected_unverified')).toBe('Connected, send a test message');
    expect(stageLabel('live_unrouted')).toBe('Live, no one is set to reply');
    expect(stageLabel('degraded')).toBe('Has problems');
    expect(stageLabel('live_unrouted')).not.toMatch(/_/);
    expect(stageLabel('something_new')).toBe('Setting up');
    expect(stageLabel(null)).toBe('Setting up');
  });
});
