// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest';
import { postToHost } from '../bridge';
import { initEmbedTheme } from '../theme';

const A = 'https://a.example';
const B = 'https://b.example';

afterEach(() => {
  vi.restoreAllMocks();
  window.history.replaceState({}, '', '/');
});

it('sends guest.ready to each allowed origin, then only to the host.init origin', () => {
  const postMessage = vi.fn();
  const parent = { postMessage } as unknown as Window;
  vi.spyOn(window, 'parent', 'get').mockReturnValue(parent);
  (window as unknown as { frappe: unknown }).frappe = { boot: { huf_embed: { allowed_origins: [A, B] } } };
  // Matched like the server does: any case, repeated slashes.
  window.history.replaceState({}, '', `${window.location.origin}//HUF//Embed/flow/f1`);

  const stop = initEmbedTheme();
  expect(postMessage.mock.calls.map(([m, o]) => [m.type, o])).toEqual([['guest.ready', A], ['guest.ready', B]]);

  const event = new MessageEvent('message', { data: { ns: 'huf.flow.embed', v: 1, type: 'host.init', payload: {} }, origin: B });
  Object.defineProperty(event, 'source', { value: parent });
  window.dispatchEvent(event);
  postMessage.mockClear();
  postToHost('guest.dirty', { flow_id: 'f1', dirty: true });
  expect(postMessage.mock.calls.map(([, o]) => o)).toEqual([B]);
  stop();
});
