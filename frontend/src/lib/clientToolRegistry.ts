/**
 * Client Tool Registry
 *
 * A framework-free registry for browser-executed agent tools ("frontend tools").
 * The backend can ask the browser to execute a named function via the
 * `frontend_tool_call_initiated` socket event; handlers registered here (or
 * exposed on `window`) are looked up and invoked to produce a result that is
 * sent back to the backend.
 */

export type ClientToolHandler = (params: Record<string, unknown>) => unknown | Promise<unknown>;

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
 * Falls back to `window[name]` for backward compatibility with the documented
 * window-level extension point, when no handler has been explicitly registered.
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
    const candidate = (window as unknown as Record<string, unknown>)[name];
    if (typeof candidate === 'function') {
      return candidate as ClientToolHandler;
    }
  } catch {
    return undefined;
  }

  return undefined;
}

/**
 * Whether a handler is available for the given tool name, either registered
 * explicitly or present as a callable `window[name]`.
 */
export function hasClientTool(name: string): boolean {
  return getClientTool(name) !== undefined;
}
