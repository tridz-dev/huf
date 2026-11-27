/**
 * Minimal guest side of the embed message protocol (docs/flow/BUILDER_EMBED.md,
 * section 4). Payloads are ids, numbers, booleans and fixed enums, never flow
 * content or server text (G4).
 */

export type NavigateTarget = 'flow_list' | 'connections' | 'providers' | 'gateways' | 'procedure';

export type ErrorCode =
  | 'session_expired' | 'not_permitted' | 'not_found' | 'unknown_app'
  | 'load_failed' | 'save_failed' | 'publish_refused';

export type FlowStatusName = 'Draft' | 'Active';

type GuestMessage = {
  'guest.ready': Record<string, never>;
  'guest.loaded': { flow_id: string; version: number; status: FlowStatusName; can_write: boolean };
  'guest.dirty': { flow_id: string; dirty: boolean };
  'guest.saved': { flow_id: string; version: number; unfinished: number };
  'guest.publish_state': { flow_id: string; status: FlowStatusName };
  'guest.navigate': { target: NavigateTarget };
  'guest.error': { code: ErrorCode; flow_id?: string };
};

/** The origin that answered with `host.init`; until then every allowed origin is tried. */
let hostOrigin: string | null = null;

export function setHostOrigin(origin: string | null) {
  hostOrigin = origin;
}

export function isEmbedPath(pathname: string = window.location.pathname): boolean {
  return /^\/+huf\/+embed(\/|$)/i.test(pathname);
}

/** Boot data the server adds only to embed responses, after its frame and access checks. */
export function embedBoot(): { allowed_origins: string[] } | null {
  const boot = (window as unknown as {
    frappe?: { boot?: { huf_embed?: { allowed_origins?: unknown } } };
  }).frappe?.boot?.huf_embed;
  const origins = boot?.allowed_origins;
  if (!Array.isArray(origins)) return null;
  return { allowed_origins: origins.filter((o): o is string => typeof o === 'string' && o !== '*') };
}

/** After `host.init`, post to that origin only; before it, to each allowed one (the browser drops mismatches). */
export function postToHost<T extends keyof GuestMessage>(type: T, payload: GuestMessage[T]): void {
  if (window.parent === window) return;
  const allowed = embedBoot()?.allowed_origins ?? [];
  for (const origin of hostOrigin && allowed.includes(hostOrigin) ? [hostOrigin] : allowed) {
    window.parent.postMessage({ ns: 'huf.flow.embed', v: 1, type, payload }, origin);
  }
}
