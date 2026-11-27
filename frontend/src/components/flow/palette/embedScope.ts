/**
 * The step types the embedded editor may offer (docs/flow/BUILDER_EMBED.md section 3). Outside `/huf/embed/` there is no
 * scope. Inside, `?app=` is read once and nothing is allowed until the server has sent the list (fail closed).
 * This narrows the palette only; the server's publish checks decide what a flow may contain.
 */

/** `null`: not the embedded editor. `''`: embedded without a usable `app`. */
export function readEmbedApp(loc: { pathname: string; search: string }): string | null {
  if (!/\/embed\/+flow\//i.test(loc.pathname)) return null;
  const app = new URLSearchParams(loc.search).get('app') ?? '';
  return /^[a-z][a-z0-9_]*$/.test(app) ? app : '';
}

let app: string | null = typeof window === 'undefined' ? null : readEmbedApp(window.location);
let allowed: ReadonlySet<string> = new Set();

export const embedApp = (): string | null => app;
/** For the embed page and tests: sets the app and forgets the allowed list. */
export function setEmbedApp(next: string | null) {
  app = next;
  allowed = new Set();
}
export function setScopeTypes(types: string[]) {
  allowed = new Set(types);
}
export const isBackendTypeAllowed = (type: string): boolean => app === null || allowed.has(type);
