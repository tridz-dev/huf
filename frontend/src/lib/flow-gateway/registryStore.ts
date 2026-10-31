import type { GatewayRegistry } from './gatewayTrigger.types';

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
