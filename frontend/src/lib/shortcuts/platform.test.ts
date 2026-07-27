import { describe, expect, it } from 'vitest';
import { detectPlatform, getModifierKey } from './platform';

describe('detectPlatform', () => {
  it('detects mac from userAgentData.platform', () => {
    expect(detectPlatform({ userAgentData: { platform: 'macOS' } })).toBe('mac');
  });

  it('detects mac from navigator.platform when userAgentData is unavailable', () => {
    expect(detectPlatform({ platform: 'MacIntel' })).toBe('mac');
  });

  it('falls back to userAgent when platform is unavailable', () => {
    expect(
      detectPlatform({ userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' })
    ).toBe('mac');
  });

  it('detects linux', () => {
    expect(detectPlatform({ platform: 'Linux x86_64' })).toBe('linux');
  });

  it('defaults to windows for windows hints and unknown input', () => {
    expect(detectPlatform({ platform: 'Win32' })).toBe('windows');
    expect(detectPlatform({})).toBe('windows');
  });

  it('prefers userAgentData over the legacy platform fallback', () => {
    expect(detectPlatform({ userAgentData: { platform: 'Linux' }, platform: 'MacIntel' })).toBe(
      'linux'
    );
  });
});

describe('getModifierKey', () => {
  it('returns Cmd/Option symbols on mac', () => {
    expect(getModifierKey('mac')).toEqual({
      platform: 'mac',
      mod: '⌘',
      modLabel: 'Cmd',
      alt: '⌥',
      altLabel: 'Option',
    });
  });

  it('returns Ctrl/Alt labels on windows and linux', () => {
    expect(getModifierKey('windows')).toMatchObject({ mod: 'Ctrl', alt: 'Alt' });
    expect(getModifierKey('linux')).toMatchObject({ mod: 'Ctrl', alt: 'Alt' });
  });
});
