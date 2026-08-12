/**
 * Client Tool Registry
 *
 * A framework-free registry for browser-executed agent tools ("frontend tools").
 * The backend can ask the browser to execute a named function via the
 * `frontend_tool_call_initiated` socket event; handlers registered here (or
 * exposed on the `window.hufClientTools` namespace) are looked up and invoked
 * to produce a result that is sent back to the backend.
 *
 * `window.hufClientTools` is the supported extension point for pages/scripts
 * that want to expose a tool without importing `registerClientTool` directly.
 * Arbitrary DOM globals (`window.open`, `window.fetch`, etc.) are never
 * resolved as tools — only functions explicitly placed on this namespace.
 */

export type ClientToolHandler = (params: Record<string, unknown>) => unknown | Promise<unknown>;

declare global {
  interface Window {
    hufClientTools?: Record<string, ClientToolHandler>;
  }
}

const registry = new Map<string, ClientToolHandler>();

/**
 * Register a handler for a client-executed tool.
 * Returns a function that unregisters the handler.
 */
export function registerClientTool(name: string, handler: ClientToolHandler): () => void {
  registry.set(name, handler);
  return () => {
    if (registry.get(name) === handler) {
      registry.delete(name);
    }
  };
}

/**
 * Look up a handler for a client-executed tool.
 *
 * Falls back to `window.hufClientTools[name]`, the documented namespaced
 * extension point, when no handler has been explicitly registered. This
 * never resolves to arbitrary DOM globals (e.g. `window.open`), which would
 * let a model-supplied tool name invoke unrelated browser APIs.
 */
export function getClientTool(name: string): ClientToolHandler | undefined {
  const registered = registry.get(name);
  if (registered) {
    return registered;
  }

  if (typeof window === 'undefined') {
    return undefined;
  }

  try {
    const candidate = window.hufClientTools?.[name];
    if (typeof candidate === 'function') {
      return candidate;
    }
  } catch {
    return undefined;
  }

  return undefined;
}

/**
 * Whether a handler is available for the given tool name, either registered
 * explicitly or present as a callable `window.hufClientTools[name]`.
 */
export function hasClientTool(name: string): boolean {
  return getClientTool(name) !== undefined;
}
