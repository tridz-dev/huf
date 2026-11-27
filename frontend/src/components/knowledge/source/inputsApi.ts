import { apiCall } from '@/lib/api';

const INPUTS_API = 'huf.ai.knowledge.api.inputs';

export interface BulkDeleteResult {
  deleted: string[];
  failed: Array<{ name: string; error: string }>;
}

/** Delete several inputs of one source; stats are refreshed once on the server. */
export function bulkDeleteInputs(knowledgeSource: string, inputs: string[]): Promise<BulkDeleteResult> {
  return apiCall<BulkDeleteResult>(`${INPUTS_API}.bulk_delete_inputs`, { knowledge_source: knowledgeSource, inputs }, { verb: 'POST' });
}

export interface IndexedChunk {
  index: number;
  text: string;
  page?: number | null;
  page_end?: number | null;
}

export interface InputChunksPage {
  /** False when the source's search backend cannot list its stored text. */
  supported: boolean;
  chunks: IndexedChunk[];
  total: number;
  start: number;
  limit: number;
}

export const CHUNKS_PAGE_SIZE = 10;

/** One page of the text indexed for an input. */
export function getInputChunks(knowledgeInput: string, start = 0, limit = CHUNKS_PAGE_SIZE): Promise<InputChunksPage> {
  return apiCall<InputChunksPage>(`${INPUTS_API}.get_input_chunks`, { knowledge_input: knowledgeInput, start, limit }, { verb: 'GET' });
}
