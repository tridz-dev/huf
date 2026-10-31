import type { GatewayChoice, GatewayRegistry } from './gatewayTrigger.types';

/**
 * The session's copy of the chat trigger registry. Pure and synchronous so wording and validation (which are plain
 * functions) can read it; `services/gatewayTriggerApi.ts` fills it. Null until the first answer.
 */
let current: GatewayRegistry | null = null;
const listeners = new Set<() => void>();

export const peekGatewayRegistry = (): GatewayRegistry | null => current;

export function setGatewayRegistry(next: GatewayRegistry | null): void {
  current = next;
  listeners.forEach((l) => l());
}

export const onGatewayRegistryChange = (fn: () => void): (() => void) => {
  listeners.add(fn);
  return () => void listeners.delete(fn);
};

/**
 * Channel on/off states for people who can only look at flows (they cannot list channels). Enough for the checklist
 * ("switched off") but not a registry: no option specs, so the editor forms never read it.
 */
let viewerGateways: GatewayChoice[] = [];
let viewerRegistry: GatewayRegistry | null = null;

export function setViewerGateways(list: GatewayChoice[]): void {
  viewerGateways = list;
  viewerRegistry = list.length
    ? { version: 0, limits: { max_params: 0, max_list_items: 0, max_text: 0, max_item_text: 0 }, specs: {} as GatewayRegistry['specs'], gateways: list }
    : null;
  listeners.forEach((l) => l());
}

export const peekViewerGateways = (): GatewayChoice[] => viewerGateways;

/** What a checklist reads: the full registry for editors, else the view-only channel states (or nothing). */
export const peekIssueRegistry = (): GatewayRegistry | null => current ?? viewerRegistry;
