/**
 * Minimal guest side of the embed message protocol (docs/flow/BUILDER_EMBED.md,
 * section 4). Only the messages the embed route itself needs; payloads are fixed
 * enums, never flow content or server text (G4).
 */

export type NavigateTarget = 'flow_list' | 'connections' | 'providers' | 'gateways' | 'procedure';

type GuestMessage = {
  'guest.navigate': { target: NavigateTarget };
  'guest.error': { code: 'session_expired' };
};

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

/** Post to each allowed origin; the browser drops the ones that are not the parent. */
export function postToHost<T extends keyof GuestMessage>(type: T, payload: GuestMessage[T]): void {
  if (window.parent === window) return;
  for (const origin of embedBoot()?.allowed_origins ?? []) {
    window.parent.postMessage({ ns: 'huf.flow.embed', v: 1, type, payload }, origin);
  }
}
