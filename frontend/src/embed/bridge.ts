/**
 * Minimal guest side of the embed message protocol (docs/flow/BUILDER_EMBED.md,
 * section 4). Payloads are ids, numbers, booleans and fixed enums, never flow
 * content or server text (G4).
 */

export type NavigateTarget =
  | 'flow_list' | 'connections' | 'providers' | 'gateways' | 'procedure'
  /** A run of this flow; the only target that carries an id (`run_id`). */
  | 'run'
  /** The host's approval list. */
  | 'approvals';

export type NavigatePayload = { target: Exclude<NavigateTarget, 'run'> } | { target: 'run'; run_id: string };

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
  'guest.navigate': NavigatePayload;
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

/** What an app-owned flow allows in the frame (server boot, H-W7-09). Booleans and fixed values only. */
export interface EmbedPolicy {
  publish: 'host';
  test: 'dry_run';
  can_edit: boolean;
  can_test: boolean;
  can_approve: boolean;
}

/** The policy for an app-owned flow, or null for a Huf-native flow or outside the embed. */
export function embedPolicy(): EmbedPolicy | null {
  if (!embedBoot()) return null;
  const policy = (window as unknown as {
    frappe?: { boot?: { huf_embed?: { policy?: Record<string, unknown> } } };
  }).frappe?.boot?.huf_embed?.policy;
  if (!policy || typeof policy !== 'object') return null;
  return {
    publish: 'host',
    test: 'dry_run',
    can_edit: policy.can_edit === true,
    can_test: policy.can_test === true,
    can_approve: policy.can_approve === true,
  };
}
