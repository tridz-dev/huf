// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { publishComposerMode, resetComposerModes, resolveComposerMode, useComposerMode } from './composer/composerMode';

describe('resolveComposerMode', () => {
  it('treats voice calls off as text only, even with modality Both (the default)', () => {
    expect(resolveComposerMode({ agent_modality: 'Both', voice_enabled: 0 })).toBe('text');
    expect(resolveComposerMode({ agent_modality: 'Voice', voice_enabled: 0 })).toBe('text');
  });
  it('treats modality Text as text only', () => {
    expect(resolveComposerMode({ agent_modality: 'Text', voice_enabled: 1 })).toBe('text');
  });
  it('maps voice only and text and voice', () => {
    expect(resolveComposerMode({ agent_modality: 'Voice', voice_enabled: 1 })).toBe('voice');
    expect(resolveComposerMode({ agent_modality: 'Both', voice_enabled: 1 })).toBe('both');
  });
  it('keeps the full composer while the agent is unknown', () => {
    expect(resolveComposerMode(undefined)).toBe('both');
  });
});

describe('useComposerMode', () => {
  beforeEach(() => act(() => resetComposerModes()));
  it('follows the agent without reload and reacts to later publishes', () => {
    act(() => {
      publishComposerMode('A', { agent_modality: 'Text', voice_enabled: 0 });
      publishComposerMode('B', { agent_modality: 'Voice', voice_enabled: 1 });
    });
    const { result, rerender } = renderHook(({ n }) => useComposerMode(n), { initialProps: { n: 'A' } });
    expect(result.current).toBe('text');
    rerender({ n: 'B' });
    expect(result.current).toBe('voice');
    rerender({ n: 'C' });
    expect(result.current).toBe('both');
    act(() => publishComposerMode('C', { agent_modality: 'Both', voice_enabled: 0 }));
    expect(result.current).toBe('text');
  });
});
