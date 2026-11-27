// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { initTheme, setHostColorMode } from '../lib/personalization';
import {
  HOST_THEME_TOKENS,
  applyHostAppearance,
  initEmbedTheme,
  parseAppearanceParams,
  parseThemeMessage,
  sanitizeThemeTokens,
  type HostThemeTokens,
} from './theme';

const root = document.documentElement;
const SAMPLE = { colour: '#2563eb', length: '12px', font: "'Inter', sans-serif" };

const message = (payload: unknown, type = 'host.theme') => ({
  ns: 'huf.flow.embed',
  v: 1,
  type,
  payload,
});

const encode = (value: unknown) => Buffer.from(JSON.stringify(value)).toString('base64url');

let onSystemChange: () => void = () => {};

beforeEach(() => {
  window.matchMedia = vi.fn().mockReturnValue({
    matches: true,
    addEventListener: (_: string, handler: () => void) => {
      onSystemChange = handler;
    },
  }) as unknown as typeof window.matchMedia;
});

afterEach(() => {
  setHostColorMode(null);
  root.removeAttribute('style');
  root.removeAttribute('data-theme');
  vi.restoreAllMocks();
});

describe('token mapping', () => {
  it('sets the Huf variable for every token', () => {
    const tokens = Object.fromEntries(
      Object.entries(HOST_THEME_TOKENS).map(([name, [, kind]]) => [name, SAMPLE[kind]]),
    ) as HostThemeTokens;
    applyHostAppearance({ tokens });
    for (const [variable, kind] of Object.values(HOST_THEME_TOKENS)) {
      expect(root.style.getPropertyValue(variable)).toBe(SAMPLE[kind]);
    }
    expect(Object.keys(HOST_THEME_TOKENS)).toHaveLength(18);
  });

  it('ignores unknown names, including CSS variable names', () => {
    expect(sanitizeThemeTokens({ '--paper': '#fff', shadow: '#fff', constructor: '#fff' })).toEqual({});
  });

  it('accepts the allowed value forms', () => {
    const tokens = {
      surface: '#fff',
      panel: '#ffffffaa',
      text: 'rgb(1, 2, 3)',
      border: 'rgba(1,2,3,0.5)',
      primary: 'hsl(120deg 50% 40%)',
      accent: 'hsla(120, 50%, 40%, 0.2)',
      radius: '0',
      'radius-sm': '32px',
    };
    expect(sanitizeThemeTokens(tokens)).toEqual(tokens);
  });

  it.each([
    ['surface', 'url(https://a.example/x.png)'],
    ['surface', 'var(--ink)'],
    ['surface', 'red;}'],
    ['surface', 'rgb(var(--x))'],
    ['surface', '#ffff'],
    ['radius', '33px'],
    ['radius', '-1px'],
    ['radius', '1em'],
    ['font-body', 'a'.repeat(201)],
    ['font-body', 'serif; color: red'],
    ['font-body', 'url(x)'],
  ])('drops %s = %s', (name, value) => {
    expect(sanitizeThemeTokens({ [name]: value })).toEqual({});
  });

  it('replaces the previous token set and leaves it when tokens are omitted', () => {
    applyHostAppearance({ tokens: { surface: '#111' } });
    applyHostAppearance({ mode: 'dark' });
    expect(root.style.getPropertyValue('--paper')).toBe('#111');
    applyHostAppearance({ tokens: { text: '#222' } });
    expect(root.style.getPropertyValue('--paper')).toBe('');
    expect(root.style.getPropertyValue('--ink')).toBe('#222');
  });

  it('leaves the root unstyled without tokens', () => {
    applyHostAppearance({});
    expect(root.getAttribute('style')).toBeNull();
  });
});

describe('mode', () => {
  it('switches data-theme without writing localStorage', () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem');
    applyHostAppearance({ mode: 'dark' });
    expect(root.getAttribute('data-theme')).toBe('midnight');
    applyHostAppearance({ mode: 'light' });
    expect(root.hasAttribute('data-theme')).toBe(false);
    expect(setItem).not.toHaveBeenCalled();
  });

  it('is not overridden by a later system or tab theme change', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockReturnValue('system');
    initTheme();
    expect(root.getAttribute('data-theme')).toBe('midnight');
    applyHostAppearance({ mode: 'light' });
    onSystemChange();
    window.dispatchEvent(new StorageEvent('storage', { key: 'huf.color-scheme' }));
    expect(root.hasAttribute('data-theme')).toBe(false);
  });
});

describe('URL parameters', () => {
  it('reads mode and base64url theme', () => {
    const search = `?mode=dark&theme=${encode({ accent: '#2563eb', nope: '1' })}`;
    expect(parseAppearanceParams(search)).toEqual({ mode: 'dark', tokens: { accent: '#2563eb' } });
  });

  it.each(['?mode=sepia&theme=%25%25', `?theme=${encode('x')}`, '?theme=bm90anNvbg'])(
    'ignores bad input %s',
    (search) => {
      expect(parseAppearanceParams(search)).toEqual({ mode: undefined, tokens: undefined });
    },
  );

  it('ignores a theme over 2 KB', () => {
    const theme = encode({ accent: '#fff', pad: 'a'.repeat(2048) });
    expect(parseAppearanceParams(`?theme=${theme}`).tokens).toBeUndefined();
  });
});

describe('messages', () => {
  it('accepts host.init and host.theme', () => {
    expect(parseThemeMessage(message({ mode: 'dark' }, 'host.init'))).toEqual({ mode: 'dark' });
    expect(parseThemeMessage(message({ tokens: { text: '#000' }, extra: 1 }))).toEqual({
      tokens: { text: '#000' },
    });
  });

  it.each([
    null,
    { ...message({}), ns: 'other' },
    { ...message({}), v: 2 },
    message({}, 'host.save'),
    message(null),
    message({ mode: 'sepia' }),
    message({ tokens: 'x' }),
    message({ pad: 'a'.repeat(9000) }),
  ])('rejects invalid message %#', (data) => {
    expect(parseThemeMessage(data)).toBeNull();
  });

  describe('listener', () => {
    const parent = {} as Window;
    const origin = 'https://host.example';
    let stop = () => {};

    const send = (source: Window, from: string) => {
      const event = new MessageEvent('message', { data: message({ tokens: { text: '#123' } }), origin: from });
      Object.defineProperty(event, 'source', { value: source });
      window.dispatchEvent(event);
      return root.style.getPropertyValue('--ink');
    };

    beforeEach(() => {
      window.history.replaceState({}, '', '/huf/embed/flow/f1?mode=dark');
      vi.spyOn(window, 'parent', 'get').mockReturnValue(parent);
      (window as unknown as { frappe: unknown }).frappe = {
        boot: { huf_embed: { allowed_origins: [origin] } },
      };
      stop = initEmbedTheme();
    });

    afterEach(() => {
      stop();
      window.history.replaceState({}, '', '/');
      delete (window as unknown as { frappe?: unknown }).frappe;
    });

    it('applies the URL mode and only trusted messages', () => {
      expect(root.getAttribute('data-theme')).toBe('midnight');
      expect(send(parent, 'https://evil.example')).toBe('');
      expect(send({} as Window, origin)).toBe('');
      expect(send(parent, origin)).toBe('#123');
    });
  });

  it('does nothing outside the embed route', () => {
    window.history.replaceState({}, '', '/huf/flows/f1?mode=dark');
    initEmbedTheme();
    expect(root.hasAttribute('data-theme')).toBe(false);
    window.history.replaceState({}, '', '/');
  });
});
