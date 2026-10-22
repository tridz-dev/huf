import { useEffect, useMemo, useState } from 'react';
import { Toaster } from '@/components/ui/sonner';
import { TelegramApp } from '@/components/telegram-app/TelegramApp';
import { NotInTelegram } from '@/components/telegram-app/NotInTelegram';
import { resolveGateway, themeVars } from '@/components/telegram-app/model';
import { loadTelegramScript, MOCK_ENABLED, mockWebApp, type TgWebApp } from '@/components/telegram-app/telegramWebApp';
import {
  authenticate, getConfig, resetTelegramAppSession, TelegramAppError, type TgConfig,
} from '@/services/telegramAppApi';

type State =
  | { kind: 'loading' }
  | { kind: 'no-telegram' }
  | { kind: 'error'; message: string }
  | { kind: 'signed-out' }
  | { kind: 'ready'; config: TgConfig | null; roleScope: string; gateway: string };

/** Standalone Telegram Mini App (auth: Telegram initData, not a Frappe session). */
export default function TelegramAppPage() {
  const [state, setState] = useState<State>({ kind: 'loading' });
  const [app, setApp] = useState<TgWebApp | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      const wa = MOCK_ENABLED() ? mockWebApp() : await loadTelegramScript();
      if (!alive) return;
      if (!wa || !wa.initData) { setState({ kind: 'no-telegram' }); return; }
      setApp(wa);
      try { wa.ready?.(); wa.expand?.(); } catch { /* optional */ }
      const gw = resolveGateway(window.location.search, wa.initDataUnsafe?.start_param);
      if (!gw) { setState({ kind: 'error', message: 'No gateway was provided.' }); return; }
      try {
        const auth = await authenticate(wa.initData, gw);
        const config = await getConfig().catch(() => null);
        if (alive) setState({ kind: 'ready', config, roleScope: auth.role_scope, gateway: auth.gateway });
      } catch (e) {
        if (alive) setState({ kind: 'error', message: e instanceof TelegramAppError ? e.message : 'Could not sign in.' });
      }
    })();
    return () => { alive = false; resetTelegramAppSession(); };
  }, []);

  const style = useMemo(() => {
    const dark = app?.colorScheme === 'dark';
    const base: Record<string, string> = dark
      ? { '--tg-bg': '#18222d', '--tg-text': '#ffffff', '--tg-hint': '#8b98a5', '--tg-button': '#3390ec',
          '--tg-secondary-bg': '#232e3c', '--tg-section-bg': '#232e3c', '--tg-destructive': '#ec3942' }
      : { '--tg-bg': '#ffffff', '--tg-text': '#111111', '--tg-hint': '#707579', '--tg-button': '#2481cc',
          '--tg-secondary-bg': '#f1f1f4', '--tg-section-bg': '#f4f4f7', '--tg-destructive': '#d32f2f' };
    return { ...base, ...themeVars(app?.themeParams), backgroundColor: 'var(--tg-bg)', color: 'var(--tg-text)' } as React.CSSProperties;
  }, [app]);

  let body;
  if (state.kind === 'loading') body = <p className="p-6 text-center text-sm">Loading...</p>;
  else if (state.kind === 'no-telegram') body = <NotInTelegram />;
  else if (state.kind === 'signed-out') body = <NotInTelegram message="You are signed out. Reopen the app from Telegram." />;
  else if (state.kind === 'error') body = <NotInTelegram title="Could not sign in" message={state.message} />;
  else body = (
    <TelegramApp
      config={state.config}
      roleScope={state.roleScope}
      gateway={state.gateway}
      onSignedOut={() => setState({ kind: 'signed-out' })}
    />
  );

  return (
    <div style={style} className="min-h-screen">
      {body}
      <Toaster position="top-center" />
    </div>
  );
}
