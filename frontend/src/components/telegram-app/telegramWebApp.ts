/** Thin, defensive wrapper over window.Telegram.WebApp. */
export interface TgWebApp {
  initData: string;
  initDataUnsafe?: { start_param?: string };
  colorScheme?: 'light' | 'dark';
  themeParams?: Record<string, string>;
  ready?: () => void;
  expand?: () => void;
  onEvent?: (e: string, cb: () => void) => void;
  offEvent?: (e: string, cb: () => void) => void;
  BackButton?: { show: () => void; hide: () => void; onClick: (cb: () => void) => void; offClick: (cb: () => void) => void };
  MainButton?: {
    setText: (t: string) => void; show: () => void; hide: () => void;
    onClick: (cb: () => void) => void; offClick: (cb: () => void) => void;
    showProgress?: () => void; hideProgress?: () => void;
  };
  HapticFeedback?: {
    notificationOccurred: (t: 'error' | 'success' | 'warning') => void;
    impactOccurred?: (s: 'light' | 'medium' | 'heavy') => void;
  };
}

declare global { interface Window { Telegram?: { WebApp?: TgWebApp } } }

const SCRIPT_SRC = 'https://telegram.org/js/telegram-web-app.js';

export const MOCK_ENABLED = (): boolean =>
  import.meta.env.DEV && new URLSearchParams(window.location.search).get('mock') === '1';

export function getWebApp(): TgWebApp | null {
  return window.Telegram?.WebApp ?? null;
}

export function loadTelegramScript(timeoutMs = 4000): Promise<TgWebApp | null> {
  if (getWebApp()) return Promise.resolve(getWebApp());
  return new Promise((resolve) => {
    const s = document.createElement('script');
    s.src = SCRIPT_SRC;
    s.async = true;
    const done = () => resolve(getWebApp());
    s.onload = done;
    s.onerror = () => resolve(null);
    document.head.appendChild(s);
    setTimeout(done, timeoutMs);
  });
}

export function haptic(kind: 'success' | 'error' | 'warning'): void {
  try { getWebApp()?.HapticFeedback?.notificationOccurred(kind); } catch { /* optional */ }
}

export function mockWebApp(): TgWebApp {
  return { initData: 'mock', initDataUnsafe: { start_param: '' }, colorScheme: 'light', themeParams: {} };
}
