/** Pure helpers for the Telegram Mini App UI. */
import { TelegramAppError, type TgConfig, type TgDocField } from '@/services/telegramAppApi';

export function resolveGateway(search: string, startParam?: string | null): string {
  const gw = new URLSearchParams(search).get('gw');
  return (gw || startParam || '').trim();
}

export function canAct(cfg: TgConfig | null): boolean {
  return !!cfg?.features?.act;
}

export function doctypeChoices(cfg: TgConfig | null): string[] {
  return (cfg?.doctypes ?? []).map((d) => d.name);
}

/** Case-insensitive substring filter for the record-type picker. */
export function filterChoices(choices: string[], query: string, max = 8): string[] {
  const q = query.trim().toLowerCase();
  return (q ? choices.filter((c) => c.toLowerCase().includes(q)) : choices).slice(0, max);
}

/** Render any field value as plain text (React escapes it; never HTML). */
export function formatFieldValue(f: TgDocField): string {
  const v = f.value;
  if (v === null || v === undefined || v === '') return '-';
  if (typeof v === 'boolean') return v ? 'Yes' : 'No';
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}

export function actionLabel(a: string): string { return a; }

/** Reject/cancel-style transitions get the destructive treatment. */
export function isDestructiveAction(a: string): boolean {
  return /reject|cancel|decline|deny|close/i.test(a);
}
export function isApproveAction(a: string): boolean {
  return /approv|accept|submit|confirm/i.test(a);
}

export function pendingCount(items: { actions: string[] }[]): number { return items.length; }

export function themeVars(p: Record<string, string> | undefined): Record<string, string> {
  if (!p) return {};
  const map: Record<string, string> = {
    bg_color: '--tg-bg', text_color: '--tg-text', hint_color: '--tg-hint', link_color: '--tg-link',
    button_color: '--tg-button', button_text_color: '--tg-button-text',
    secondary_bg_color: '--tg-secondary-bg', destructive_text_color: '--tg-destructive',
    section_bg_color: '--tg-section-bg',
  };
  const out: Record<string, string> = {};
  for (const [k, css] of Object.entries(map)) {
    const v = p[k];
    if (typeof v === 'string' && /^#[0-9a-fA-F]{3,8}$/.test(v)) out[css] = v;
  }
  return out;
}

/** The server answers every sign-in refusal the same way, so a refused first sign-in means this account is not linked. */
export function signInFailure(e: unknown): { kind: 'error'; title: string; message: string } {
  const title = 'Could not sign in';
  if (e instanceof TelegramAppError && e.code === 'unauthorized') {
    return { kind: 'error', title: 'Not linked yet', message: 'This Telegram account is not linked to Huf yet. Ask an admin to link it, then try again.' };
  }
  return { kind: 'error', title, message: e instanceof TelegramAppError ? e.message : 'Something went wrong. Try again.' };
}
