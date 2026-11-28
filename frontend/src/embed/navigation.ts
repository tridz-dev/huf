import type { NavigatePayload, NavigateTarget } from './bridge';

export type EmbedNavigation =
  | { kind: 'stay' }
  | { kind: 'rewrite'; to: string }
  | { kind: 'leave'; target: NavigatePayload | null };

type PlainTarget = Exclude<NavigateTarget, 'run'>;

const TARGETS: Array<[string, PlainTarget]> = [
  ['flows', 'flow_list'],
  ['integrations', 'connections'],
  ['providers', 'providers'],
  ['models', 'providers'],
  ['gateways', 'gateways'],
  ['channels', 'gateways'],
  ['procedures', 'procedure'],
  ['approvals', 'approvals'],
];

function segments(pathname: string): string[] {
  const parts = pathname.split('/').filter(Boolean);
  return parts[0] === 'huf' ? parts.slice(1) : parts;
}

function decode(part: string | undefined): string {
  try {
    return decodeURIComponent(part ?? '');
  } catch {
    return part ?? '';
  }
}

/** Where a Huf screen path (without `/huf`) sends the host, if anywhere. */
function leaveTarget(there: string[], search: string): NavigatePayload | null {
  if (there[0] === 'executions') {
    if (there[1]) return { target: 'run', run_id: decode(there[1]) };
    return new URLSearchParams(search).get('tab') === 'approvals' ? { target: 'approvals' } : null;
  }
  const found = TARGETS.find(([root]) => root === there[0])?.[1];
  return found ? { target: found } : null;
}

/** What the embedded editor does with an in-app navigation (router paths, without basename). */
export function classifyEmbedNavigation(
  current: { pathname: string; search: string },
  next: { pathname: string; search: string },
): EmbedNavigation {
  const here = segments(current.pathname);
  const there = segments(next.pathname);
  if (here.join('/') === there.join('/')) return { kind: 'stay' };

  // A link to a run of this same flow stays in the frame, keeping `app` and appearance.
  const sameFlow = here[0] === 'embed' && there[0] === 'flows' && !!there[1] && decode(there[1]) === decode(here[2]);
  if (sameFlow) {
    const params = new URLSearchParams(current.search);
    params.delete('run');
    new URLSearchParams(next.search).forEach((value, key) => params.set(key, value));
    const query = params.toString();
    return { kind: 'rewrite', to: `${current.pathname}${query ? `?${query}` : ''}` };
  }

  return { kind: 'leave', target: leaveTarget(there, next.search) };
}

/**
 * What a plain link (`<a href>`) inside the frame does. Links to another site keep their behaviour; every same-site link
 * outside `/huf/embed/` (a Huf screen, a desk form such as `/app/agent-flow-run/<id>`) is stopped and, where the host has a
 * matching screen, reported to it. `current` is the frame's full location path (with `/huf`).
 */
export function classifyEmbedHref(
  href: string,
  current: { pathname: string; search: string },
  origin: string = window.location.origin,
): EmbedNavigation | null {
  let url: URL;
  try {
    url = new URL(href, `${origin}${current.pathname}`);
  } catch {
    return null;
  }
  if (url.origin !== origin) return null;
  const parts = url.pathname.split('/').filter(Boolean);
  if (parts[0] === 'app') {
    if (parts[1] === 'agent-flow-run' && parts[2]) return { kind: 'leave', target: { target: 'run', run_id: decode(parts[2]) } };
    if (parts[1] === 'flow-definition') return { kind: 'leave', target: { target: 'flow_list' } };
    return { kind: 'leave', target: null };
  }
  if (parts[0] === 'huf') {
    if (parts[1] === 'embed') {
      return url.pathname === current.pathname ? { kind: 'stay' } : { kind: 'leave', target: null };
    }
    return classifyEmbedNavigation(current, { pathname: url.pathname, search: url.search });
  }
  // Assets, files and API calls are not screens; anything else on this site would replace the editor.
  if (['assets', 'files', 'private', 'api'].includes(parts[0] ?? '')) return null;
  return { kind: 'leave', target: null };
}
