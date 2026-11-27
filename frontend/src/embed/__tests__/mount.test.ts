// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import '../huf-flow-builder';

const ORIGIN = 'https://huf.example';
const msg = (type: string, payload: object, extra: object = {}) => ({ ns: 'huf.flow.embed', v: 1, type, payload, ...extra });

describe('<huf-flow-builder>', () => {
  let element: HTMLElement;
  let events: Array<[string, unknown]>;

  const frame = () => element.querySelector('iframe')!;
  const send = (data: unknown, origin = ORIGIN, source: unknown = frame().contentWindow) => {
    const event = new MessageEvent('message', { data, origin });
    Object.defineProperty(event, 'source', { value: source });
    window.dispatchEvent(event);
  };

  beforeEach(() => {
    vi.useFakeTimers();
    events = [];
    element = document.createElement('huf-flow-builder');
    for (const name of ['ready', 'saved', 'error']) {
      element.addEventListener(name, (e) => events.push([name, (e as CustomEvent).detail]));
    }
    element.setAttribute('flow', 'a b');
    element.setAttribute('app', 'happiol');
    element.setAttribute('src-origin', ORIGIN);
    element.setAttribute('theme', '{"accent":"#2563eb"}');
    document.body.append(element);
  });
  afterEach(() => {
    element.remove();
    vi.useRealTimers();
  });

  it('frames the embed route with the app scope and theme', () => {
    const url = new URL(frame().src);
    expect(url.origin + url.pathname).toBe(`${ORIGIN}/huf/embed/flow/a%20b`);
    expect(url.searchParams.get('app')).toBe('happiol');
    expect(JSON.parse(atob(url.searchParams.get('theme')!))).toEqual({ accent: '#2563eb' });
  });

  it('answers guest.ready and later theme changes at the frame origin only', () => {
    const post = vi.spyOn(frame().contentWindow!, 'postMessage').mockImplementation(() => {});
    send(msg('guest.ready', {}));
    element.setAttribute('mode', 'dark');
    expect(post.mock.calls).toEqual([
      [msg('host.init', { mode: undefined, tokens: { accent: '#2563eb' } }), ORIGIN],
      [msg('host.theme', { mode: 'dark', tokens: { accent: '#2563eb' } }), ORIGIN],
    ]);
  });

  it('ignores foreign, malformed and oversize messages', () => {
    const saved = { flow_id: 'a', version: 2, unfinished: 0 };
    send(msg('guest.saved', saved), 'https://evil.example');
    send(msg('guest.saved', saved), ORIGIN, window);
    send(msg('guest.saved', saved, { ns: 'x' }));
    send(msg('guest.saved', saved, { v: 2 }));
    send(msg('guest.saved', { ...saved, pad: 'x'.repeat(9000) }));
    send(msg('guest.saved', { ...saved, version: '2' }));
    send(msg('toString', {}));
    expect(events).toEqual([]);
    send(msg('guest.saved', { ...saved, flow_name: 'secret' }));
    expect(events).toEqual([['saved', saved]]);
  });

  it('reloads for another flow', () => {
    const first = frame();
    element.setAttribute('flow', 'other');
    expect(frame()).not.toBe(first);
    expect(element.querySelectorAll('iframe')).toHaveLength(1);
  });

  it('shows its own failure state without guest.ready, with Retry', () => {
    vi.advanceTimersByTime(20_000);
    expect(element.querySelector('iframe')).toBeNull();
    expect(events).toEqual([['error', { code: 'load_failed' }]]);
    element.querySelector('button')!.click();
    expect(frame()).toBeTruthy();
  });
});
