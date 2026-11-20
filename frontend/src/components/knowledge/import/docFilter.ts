import type { KnowledgeInputDoc } from '@/types/knowledge.types';

export type DocFilter = 'ready' | 'attention' | 'skipped';

export const DOC_FILTER_STATUS: Record<DocFilter, string> = {
  ready: 'Indexed',
  attention: 'Error',
  skipped: 'Skipped',
};

export function filterInputs(inputs: KnowledgeInputDoc[], filter: DocFilter | null): KnowledgeInputDoc[] {
  if (!filter) return inputs;
  return inputs.filter((i) => i.status === DOC_FILTER_STATUS[filter]);
}

/** Filter shown in the resource page pills: a status filter or everything. */
export type SourceFilter = DocFilter | 'all';
