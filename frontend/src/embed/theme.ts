/**
 * Host appearance for the embedded flow builder.
 * Contract: docs/flow/BUILDER_EMBED.md, sections 4.1, 4.2 and 5.
 */
import { setHostColorMode, type HostColorMode } from '../lib/personalization';
import { embedBoot, isEmbedPath, postToHost, setHostOrigin } from './bridge';

type TokenKind = 'colour' | 'length' | 'font';

/** Closed set: host token name -> [Huf CSS variable, value type]. */
export const HOST_THEME_TOKENS = {
  surface: ['--paper', 'colour'],
  'surface-sunken': ['--paper-deep', 'colour'],
  panel: ['--panel', 'colour'],
  text: ['--ink', 'colour'],
  'text-soft': ['--ink-soft', 'colour'],
  'text-muted': ['--steel', 'colour'],
  border: ['--line', 'colour'],
  primary: ['--primary', 'colour'],
  'primary-text': ['--primary-foreground', 'colour'],
  accent: ['--signal', 'colour'],
  'accent-text': ['--signal-ink', 'colour'],
  success: ['--good', 'colour'],
  warning: ['--warning', 'colour'],
  danger: ['--destructive', 'colour'],
  radius: ['--r', 'length'],
  'radius-sm': ['--r-sm', 'length'],
  'font-body': ['--body', 'font'],
  'font-display': ['--display', 'font'],
} as const satisfies Record<string, readonly [string, TokenKind]>;

export type HostThemeToken = keyof typeof HOST_THEME_TOKENS;
export type HostThemeTokens = Partial<Record<HostThemeToken, string>>;

export interface HostAppearance {
  mode?: HostColorMode;
  tokens?: HostThemeTokens;
}

const MESSAGE_NAMESPACE = 'huf.flow.embed';
const MAX_MESSAGE_BYTES = 8 * 1024;
const MAX_THEME_PARAM_LENGTH = 2 * 1024;
const MAX_FONT_LIST_LENGTH = 200;
const MAX_LENGTH_PX = 32;

const HEX_COLOUR = /^#(?:[0-9a-f]{3}|[0-9a-f]{6}|[0-9a-f]{8})$/i;
const FUNCTION_COLOUR = /^(?:rgb|hsl)a?\((?=[^)]*\d)(?:[\d.%,/+\s-]|deg|grad|rad|turn)+\)$/i;
const PIXELS = /^(\d+(?:\.\d+)?)px$/;
const FONT_LIST = /^[A-Za-z0-9 ,'"-]+$/;

const VALIDATORS: Record<TokenKind, (value: string) => boolean> = {
  colour: (value) => HEX_COLOUR.test(value) || FUNCTION_COLOUR.test(value),
  length: (value) => {
    if (value === '0') return true;
    const match = PIXELS.exec(value);
    return match !== null && Number(match[1]) <= MAX_LENGTH_PX;
  },
  font: (value) => value.length <= MAX_FONT_LIST_LENGTH && FONT_LIST.test(value),
};

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isMode(value: unknown): value is HostColorMode {
  return value === 'light' || value === 'dark';
}

/** Keeps known tokens with valid values; everything else is dropped. */
export function sanitizeThemeTokens(input: unknown): HostThemeTokens {
  const tokens: HostThemeTokens = {};
  if (!isPlainObject(input)) return tokens;
  for (const name of Object.keys(HOST_THEME_TOKENS) as HostThemeToken[]) {
    if (!Object.prototype.hasOwnProperty.call(input, name)) continue;
    const value = input[name];
    if (typeof value === 'string' && VALIDATORS[HOST_THEME_TOKENS[name][1]](value)) {
      tokens[name] = value;
    }
  }
  return tokens;
}

/** `tokens` replaces the previous set; omitted fields leave the current look. */
export function applyHostAppearance(
  { mode, tokens }: HostAppearance,
  root: HTMLElement = document.documentElement,
) {
  if (mode) setHostColorMode(mode);
  if (!tokens) return;
  const valid = sanitizeThemeTokens(tokens);
  for (const name of Object.keys(HOST_THEME_TOKENS) as HostThemeToken[]) {
    const variable = HOST_THEME_TOKENS[name][0];
    const value = valid[name];
    if (value === undefined) root.style.removeProperty(variable);
    else root.style.setProperty(variable, value);
  }
}

function decodeThemeParam(encoded: string): HostThemeTokens | undefined {
  if (encoded.length > MAX_THEME_PARAM_LENGTH || !/^[A-Za-z0-9_-]+={0,2}$/.test(encoded)) {
    return undefined;
  }
  try {
    const binary = atob(encoded.replace(/-/g, '+').replace(/_/g, '/'));
    const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
    const parsed: unknown = JSON.parse(new TextDecoder().decode(bytes));
    return isPlainObject(parsed) ? sanitizeThemeTokens(parsed) : undefined;
  } catch {
    return undefined;
  }
}

/** First-paint appearance from the `mode` and `theme` URL parameters. */
export function parseAppearanceParams(search: string): HostAppearance {
  const params = new URLSearchParams(search);
  const mode = params.get('mode');
  const theme = params.get('theme');
  return {
    mode: isMode(mode) ? mode : undefined,
    tokens: theme ? decodeThemeParam(theme) : undefined,
  };
}

/** Returns the appearance of a valid `host.init` / `host.theme` envelope, else null. */
export function parseThemeMessage(data: unknown): HostAppearance | null {
  if (!isPlainObject(data) || data.ns !== MESSAGE_NAMESPACE || data.v !== 1) return null;
  if (data.type !== 'host.init' && data.type !== 'host.theme') return null;
  const { payload } = data;
  if (!isPlainObject(payload)) return null;
  const { mode, tokens } = payload;
  if (mode !== undefined && !isMode(mode)) return null;
  if (tokens !== undefined && !isPlainObject(tokens)) return null;
  try {
    if (new TextEncoder().encode(JSON.stringify(data)).length > MAX_MESSAGE_BYTES) return null;
  } catch {
    return null;
  }
  return { mode, tokens: tokens === undefined ? undefined : sanitizeThemeTokens(tokens) };
}

/**
 * On an embed route, applies the URL appearance and then follows the host's
 * messages. Does nothing elsewhere. Returns a function that stops listening.
 */
export function initEmbedTheme(): () => void {
  const noop = () => {};
  if (!isEmbedPath()) return noop;
  applyHostAppearance(parseAppearanceParams(window.location.search));
  if (window.parent === window) return noop;

  const onMessage = (event: MessageEvent) => {
    if (event.source !== window.parent || !embedBoot()?.allowed_origins.includes(event.origin)) return;
    const appearance = parseThemeMessage(event.data);
    if (!appearance) return;
    if ((event.data as { type: string }).type === 'host.init') setHostOrigin(event.origin);
    applyHostAppearance(appearance);
  };
  window.addEventListener('message', onMessage);
  postToHost('guest.ready', {});
  return () => window.removeEventListener('message', onMessage);
}
