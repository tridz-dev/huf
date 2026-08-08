const THEME_STORAGE_KEY = 'huf.theme';
const COLOR_SCHEME_STORAGE_KEY = 'huf.color-scheme';
const SCENERY_STORAGE_KEY = 'huf.scenery.enabled';
const SCENERY_OPACITY_STORAGE_KEY = 'huf.scenery.opacity';

export const SCENERY_IMAGE_URL = import.meta.env.DEV
  ? '/assets/huf-bg.png'
  : '/assets/huf/frontend/assets/huf-bg.png';

export type HufTheme = 'winter' | 'midnight' | 'summer' | 'morning';
export type HufColorScheme = 'light' | 'dark' | 'system';

const DEFAULT_THEME: HufTheme = 'winter';
const DEFAULT_COLOR_SCHEME: HufColorScheme = 'light';
const DEFAULT_SCENERY_OPACITY = 55;

const THEME_MODES: Record<HufTheme, HufColorScheme> = {
  winter: 'light',
  midnight: 'dark',
  summer: 'light',
  morning: 'light',
};

function applyEffectiveTheme() {
  const theme = getEffectiveTheme();
  document.documentElement.setAttribute('data-theme', theme);
}

export function getTheme(): HufTheme {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY) as HufTheme | null;
    if (stored && (stored === 'winter' || stored === 'midnight' || stored === 'summer' || stored === 'morning')) {
      return stored;
    }
  } catch {
    // localStorage unavailable
  }
  return DEFAULT_THEME;
}

export function setTheme(theme: HufTheme) {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme);
    // Set the color-scheme to the natural mode of the chosen theme so the
    // selected palette is applied immediately. The user can still override
    // light/dark/system from the account menu.
    localStorage.setItem(COLOR_SCHEME_STORAGE_KEY, THEME_MODES[theme]);
  } catch {
    // ignore
  }
  applyEffectiveTheme();
}

export function getColorScheme(): HufColorScheme {
  try {
    const stored = localStorage.getItem(COLOR_SCHEME_STORAGE_KEY) as HufColorScheme | null;
    if (stored && (stored === 'light' || stored === 'dark' || stored === 'system')) {
      return stored;
    }
  } catch {
    // ignore
  }
  return DEFAULT_COLOR_SCHEME;
}

export function setColorScheme(scheme: HufColorScheme) {
  try {
    localStorage.setItem(COLOR_SCHEME_STORAGE_KEY, scheme);
  } catch {
    // ignore
  }
  applyEffectiveTheme();
}

export function getEffectiveTheme(): HufTheme {
  const scheme = getColorScheme();
  if (scheme === 'system') {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'midnight' : 'winter';
  }
  if (scheme === 'dark') {
    return 'midnight';
  }
  // light: honour the stored named theme (winter/summer/morning are all light)
  return getTheme();
}

export function initTheme() {
  applyEffectiveTheme();

  // React to OS-level changes while in system mode
  const media = window.matchMedia('(prefers-color-scheme: dark)');
  const handler = () => {
    if (getColorScheme() === 'system') {
      applyEffectiveTheme();
    }
  };
  if (media.addEventListener) {
    media.addEventListener('change', handler);
  } else if ((media as unknown as { addListener?: (cb: () => void) => void }).addListener) {
    (media as unknown as { addListener: (cb: () => void) => void }).addListener(handler);
  }

  // Keep theme in sync across open tabs
  const onStorage = (event: StorageEvent) => {
    if (event.key === THEME_STORAGE_KEY || event.key === COLOR_SCHEME_STORAGE_KEY) {
      applyEffectiveTheme();
    }
  };
  window.addEventListener('storage', onStorage);
}

export function setSceneryEnabled(enabled: boolean) {
  try {
    localStorage.setItem(SCENERY_STORAGE_KEY, enabled ? '1' : '0');
  } catch {
    // ignore
  }
}

export function isSceneryEnabled(): boolean {
  try {
    return localStorage.getItem(SCENERY_STORAGE_KEY) === '1';
  } catch {
    return false;
  }
}

export function setSceneryOpacity(opacity: number) {
  try {
    localStorage.setItem(SCENERY_OPACITY_STORAGE_KEY, String(opacity));
  } catch {
    // ignore
  }
}

export function getSceneryOpacity(): number {
  try {
    const stored = localStorage.getItem(SCENERY_OPACITY_STORAGE_KEY);
    if (stored) {
      const parsed = parseInt(stored, 10);
      if (!Number.isNaN(parsed)) {
        return Math.max(0, Math.min(100, parsed));
      }
    }
  } catch {
    // ignore
  }
  return DEFAULT_SCENERY_OPACITY;
}
