import type { NavigateTarget } from './bridge';

export type EmbedNavigation =
  | { kind: 'stay' }
  | { kind: 'rewrite'; to: string }
  | { kind: 'leave'; target: NavigateTarget | null };

const TARGETS: Array<[string, NavigateTarget]> = [
  ['flows', 'flow_list'],
  ['integrations', 'connections'],
  ['providers', 'providers'],
  ['models', 'providers'],
  ['gateways', 'gateways'],
  ['channels', 'gateways'],
  ['procedures', 'procedure'],
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

  return { kind: 'leave', target: TARGETS.find(([root]) => root === there[0])?.[1] ?? null };
}
