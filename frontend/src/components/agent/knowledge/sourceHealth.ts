import type { KnowledgeSourceDoc } from '@/types/knowledge.types';

export type SourceHealth = 'ready' | 'updating' | 'attention' | 'empty' | 'broken' | 'paused';

export interface InputCounts {
  total: number;
  indexed: number;
  pending: number;
  failed: number;
}

export const EMPTY_COUNTS: InputCounts = { total: 0, indexed: 0, pending: 0, failed: 0 };

export const HEALTH_LABEL: Record<SourceHealth, string> = {
  ready: 'Ready',
  updating: 'Updating',
  attention: 'Needs attention',
  empty: 'Empty',
  broken: 'Not working',
  paused: 'Paused',
};

export const HEALTH_HINT: Record<SourceHealth, string> = {
  ready: 'Agents can search this.',
  updating: 'Adding documents. You can still search what is ready.',
  attention: 'Some documents could not be read.',
  empty: 'Add documents to get started.',
  broken: 'Search is unavailable. Open the source to see why.',
  paused: 'Turned off. Agents cannot use it.',
};

export const HEALTH_BADGE: Record<SourceHealth, 'pill-success' | 'pill-info' | 'pill-warning' | 'pill-neutral' | 'pill-danger'> = {
  ready: 'pill-success',
  updating: 'pill-info',
  attention: 'pill-warning',
  empty: 'pill-neutral',
  broken: 'pill-danger',
  paused: 'pill-neutral',
};

/** Fold per-status Knowledge Input rows into the four numbers the health model needs. */
export function foldCounts(rows: Array<{ status: string; count: number }>): InputCounts {
  const c = { ...EMPTY_COUNTS };
  for (const r of rows) {
    if (r.status === 'Skipped') continue;
    c.total += r.count;
    if (r.status === 'Indexed') c.indexed += r.count;
    else if (r.status === 'Pending' || r.status === 'Processing') c.pending += r.count;
    else if (r.status === 'Error') c.failed += r.count;
  }
  return c;
}

export function computeHealth(
  source: Pick<KnowledgeSourceDoc, 'status' | 'disabled'>,
  counts: InputCounts,
): SourceHealth {
  if (source.disabled) return 'paused';
  if (source.status === 'Error') return 'broken';
  if (counts.total === 0) return 'empty';
  if (counts.pending > 0 || source.status === 'Indexing' || source.status === 'Rebuilding') return 'updating';
  if (counts.failed > 0) return 'attention';
  return counts.indexed > 0 ? 'ready' : 'empty';
}

/**
 * Updating sources can be attached: whatever is already indexed is searchable
 * and the rest arrives on its own. Every other non-Ready state is blocked.
 */
export function isAttachable(health: SourceHealth): boolean {
  return health === 'ready' || health === 'updating';
}

export function searchMethodLabel(knowledgeType: string): string {
  if (knowledgeType === 'sqlite_fts') return 'Keyword search';
  if (knowledgeType === 'sqlite_hybrid') return 'Keyword and meaning search';
  return 'Meaning-based search';
}
