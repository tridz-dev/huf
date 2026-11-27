/**
 * Host side of the embedded flow builder (docs/flow/BUILDER_EMBED.md, sections 4 and 7): creates the iframe, relays
 * the guest's messages and sends appearance. No framework imports: this is bundled on its own for host pages.
 */

export interface MountOptions {
  flow: string;
  app: string;
  /** Origin that serves Huf; default: the host page's origin. */
  srcOrigin?: string;
  mode?: 'light' | 'dark';
  tokens?: Record<string, string>;
  run?: string;
}

export type MountEvent = 'ready' | 'loaded' | 'dirty' | 'saved' | 'publish-state' | 'navigate' | 'error';

export interface MountHandle {
  /** Changes of flow, app, srcOrigin or run reload the frame; mode and tokens are sent to it. */
  update(options: MountOptions): void;
  destroy(): void;
}

const NAMESPACE = 'huf.flow.embed';
const MAX_MESSAGE_BYTES = 8 * 1024;
const READY_TIMEOUT_MS = 20_000;

type Check = (value: unknown) => boolean;
const text: Check = (v) => typeof v === 'string';
const count: Check = (v) => typeof v === 'number' && Number.isFinite(v);
const flag: Check = (v) => typeof v === 'boolean';
const oneOf = (...values: string[]): Check => (v) => typeof v === 'string' && values.includes(v);
const status = oneOf('Draft', 'Active');
const optional = (check: Check): Check => (v) => v === undefined || check(v);

/** Guest message type -> [DOM event, the exact payload keys and their checks]. */
const GUEST_MESSAGES: Record<string, [MountEvent, Record<string, Check>]> = {
  'guest.ready': ['ready', {}],
  'guest.loaded': ['loaded', { flow_id: text, version: count, status, can_write: flag }],
  'guest.dirty': ['dirty', { flow_id: text, dirty: flag }],
  'guest.saved': ['saved', { flow_id: text, version: count, unfinished: count }],
  'guest.publish_state': ['publish-state', { flow_id: text, status }],
  'guest.navigate': ['navigate', { target: oneOf('flow_list', 'connections', 'providers', 'gateways', 'procedure') }],
  'guest.error': ['error', {
    code: oneOf('session_expired', 'not_permitted', 'not_found', 'unknown_app', 'load_failed', 'save_failed', 'publish_refused'),
    flow_id: optional(text),
  }],
};

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** The DOM event and a copy of the known payload keys, or null for anything that is not a valid guest message. */
export function parseGuestMessage(data: unknown): { event: MountEvent; detail: Record<string, unknown> } | null {
  if (!isObject(data) || data.ns !== NAMESPACE || data.v !== 1 || !isObject(data.payload)) return null;
  if (typeof data.type !== 'string' || !Object.prototype.hasOwnProperty.call(GUEST_MESSAGES, data.type)) return null;
  try {
    if (new TextEncoder().encode(JSON.stringify(data)).length > MAX_MESSAGE_BYTES) return null;
  } catch {
    return null;
  }
  const [event, shape] = GUEST_MESSAGES[data.type];
  const detail: Record<string, unknown> = {};
  for (const [key, check] of Object.entries(shape)) {
    const value = data.payload[key];
    if (!check(value)) return null;
    if (value !== undefined) detail[key] = value;
  }
  return { event, detail };
}

function base64url(value: string): string {
  const bytes = new TextEncoder().encode(value);
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

export function buildFrameUrl({ flow, app, srcOrigin, mode, tokens, run }: MountOptions): URL {
  const url = new URL(`/huf/embed/flow/${encodeURIComponent(flow)}`, srcOrigin || window.location.origin);
  url.searchParams.set('app', app);
  if (mode) url.searchParams.set('mode', mode);
  if (tokens) url.searchParams.set('theme', base64url(JSON.stringify(tokens)));
  if (run) url.searchParams.set('run', run);
  return url;
}

const frameKey = ({ flow, app, srcOrigin, run }: MountOptions) => JSON.stringify([flow, app, srcOrigin, run]);

export function mountFlowBuilder(
  container: HTMLElement | ShadowRoot,
  initial: MountOptions,
  emit: (event: MountEvent, detail: Record<string, unknown>) => void,
): MountHandle {
  let options = initial;
  let frame: HTMLIFrameElement | null = null;
  let fallback: HTMLElement | null = null;
  let origin = '';
  let ready = false;
  let timer: ReturnType<typeof setTimeout> | undefined;

  const clear = () => {
    clearTimeout(timer);
    frame?.remove();
    fallback?.remove();
    frame = null;
    fallback = null;
    ready = false;
  };

  const send = (type: 'host.init' | 'host.theme') => {
    const payload = { mode: options.mode, tokens: options.tokens ?? {} };
    frame?.contentWindow?.postMessage({ ns: NAMESPACE, v: 1, type, payload }, origin);
  };

  const showFailure = () => {
    clear();
    fallback = document.createElement('div');
    fallback.setAttribute('role', 'alert');
    const message = document.createElement('p');
    message.textContent = 'The flow editor could not be loaded.';
    const retry = document.createElement('button');
    retry.type = 'button';
    retry.textContent = 'Retry';
    retry.addEventListener('click', load);
    fallback.append(message, retry);
    container.append(fallback);
    emit('error', { code: 'load_failed' });
  };

  function load() {
    clear();
    const url = buildFrameUrl(options);
    origin = url.origin;
    frame = document.createElement('iframe');
    frame.title = 'Flow editor';
    frame.src = url.href;
    frame.style.cssText = 'display:block;width:100%;height:100%;border:0';
    container.append(frame);
    timer = setTimeout(showFailure, READY_TIMEOUT_MS);
  }

  const onMessage = (event: MessageEvent) => {
    if (!frame || event.source !== frame.contentWindow || event.origin !== origin) return;
    const message = parseGuestMessage(event.data);
    if (!message) return;
    if (message.event === 'ready') {
      clearTimeout(timer);
      ready = true;
      send('host.init');
    }
    emit(message.event, message.detail);
  };

  window.addEventListener('message', onMessage);
  load();

  return {
    update(next) {
      const previous = options;
      options = next;
      if (frameKey(previous) !== frameKey(next)) load();
      // Before `guest.ready` there is nobody to tell; `host.init` will carry the latest values.
      else if (ready) send('host.theme');
    },
    destroy() {
      window.removeEventListener('message', onMessage);
      clear();
    },
  };
}
