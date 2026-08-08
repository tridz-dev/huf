import { useEffect, useState } from 'react';

export type Platform = 'mac' | 'windows' | 'linux';

interface NavigatorLike {
  platform?: string;
  userAgent?: string;
  userAgentData?: { platform?: string };
}

/**
 * Resolves the OS family from the platform hints available on `navigator`.
 * `userAgentData.platform` is the modern source but isn't universally
 * supported (notably Safari/Firefox), so `platform`/`userAgent` are always
 * checked as a fallback.
 */
export function detectPlatform(nav?: NavigatorLike): Platform {
  const n = nav ?? (typeof navigator !== 'undefined' ? (navigator as NavigatorLike) : undefined);
  if (!n) return 'windows';

  const hint = n.userAgentData?.platform || n.platform || n.userAgent || '';

  if (/mac|iphone|ipad|ipod/i.test(hint)) return 'mac';
  if (/linux/i.test(hint)) return 'linux';
  return 'windows';
}

export interface ModifierLabels {
  platform: Platform;
  /** Primary modifier: ⌘ on Mac, Ctrl on Windows/Linux. */
  mod: string;
  modLabel: string;
  /** Secondary modifier: ⌥ (Option) on Mac, Alt on Windows/Linux. */
  alt: string;
  altLabel: string;
}

export function getModifierKey(platform: Platform = detectPlatform()): ModifierLabels {
  if (platform === 'mac') {
    return { platform, mod: '⌘', modLabel: 'Cmd', alt: '⌥', altLabel: 'Option' };
  }
  return { platform, mod: 'Ctrl', modLabel: 'Ctrl', alt: 'Alt', altLabel: 'Alt' };
}

/** Detects the current platform, re-resolving after mount for SSR safety. */
export function usePlatform(): Platform {
  const [platform, setPlatform] = useState<Platform>(() => detectPlatform());

  useEffect(() => {
    setPlatform(detectPlatform());
  }, []);

  return platform;
}
