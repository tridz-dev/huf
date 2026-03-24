import { db, call } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import type { KnowledgeSourceDoc, KnowledgeInputDoc } from '@/types/knowledge.types';
import { handleFrappeError } from '@/lib/frappe-error';
import { fetchPaginatedCount } from './utilsApi';

// ---------------------------------------------------------------------------
// Knowledge Source
// ---------------------------------------------------------------------------

const KNOWLEDGE_SOURCE_LIST_FIELDS = [
  'name',
  'source_name',
  'description',
  'knowledge_type',
  'scope',
  'status',
  'total_chunks',
  'total_inputs',
  'last_indexed_at',
  'disabled',
];

export interface GetKnowledgeSourcesParams {
  page?: number;
  limit?: number;
  start?: number;
  search?: string;
  status?: string;
}

export interface PaginatedKnowledgeSourcesResponse {
  items: KnowledgeSourceDoc[];
  hasMore: boolean;
  total?: number;
}

export async function getKnowledgeSources(
  params?: GetKnowledgeSourcesParams,
): Promise<PaginatedKnowledgeSourcesResponse> {
  try {
    const {
      page = 1,
      limit = 20,
      start = (page - 1) * limit,
      search,
      status,
    } = params || {};

    const filters: Array<[string, string, unknown]> = [];

    if (status && status !== 'all') {
      if (status === 'disabled') {
        filters.push(['disabled', '=', 1]);
      } else {
        filters.push(['disabled', '=', 0]);
        filters.push(['status', '=', status.charAt(0).toUpperCase() + status.slice(1)]);
      }
    }

    if (search && search.trim()) {
      filters.push(['source_name', 'like', `%${search.trim()}%`]);
    }

    const sources = await db.getDocList(doctype['Knowledge Source'], {
      fields: KNOWLEDGE_SOURCE_LIST_FIELDS,
      filters: filters.length > 0 ? (filters as any) : undefined,
      limit: limit + 1,
      ...(start > 0 && { limit_start: start }),
      orderBy: { field: 'modified', order: 'desc' },
    });

    const mapped = sources as KnowledgeSourceDoc[];
    const hasMore = mapped.length > limit;
    const items = hasMore ? mapped.slice(0, limit) : mapped;

    const total = await fetchPaginatedCount(
      page,
      items.length,
      doctype['Knowledge Source'],
      filters,
    );

    return { items, hasMore, total };
  } catch (error) {
    handleFrappeError(error, 'Error fetching knowledge sources');
  }
}

export async function getKnowledgeSource(name: string): Promise<KnowledgeSourceDoc> {
  try {
    const doc = await db.getDoc(doctype['Knowledge Source'], name);
    return doc as KnowledgeSourceDoc;
  } catch (error) {
    handleFrappeError(error, `Error fetching knowledge source ${name}`);
  }
}

export async function createKnowledgeSource(
  data: Partial<KnowledgeSourceDoc>,
): Promise<KnowledgeSourceDoc> {
  try {
    const doc = await db.createDoc(doctype['Knowledge Source'], data);
    return doc as KnowledgeSourceDoc;
  } catch (error) {
    handleFrappeError(error, 'Error creating knowledge source');
  }
}

export async function updateKnowledgeSource(
  name: string,
  data: Partial<KnowledgeSourceDoc>,
): Promise<KnowledgeSourceDoc> {
  try {
    await db.updateDoc(doctype['Knowledge Source'], name, data);
    const updated = await db.getDoc(doctype['Knowledge Source'], name);
    return updated as KnowledgeSourceDoc;
  } catch (error) {
    handleFrappeError(error, `Error updating knowledge source ${name}`);
  }
}

export async function deleteKnowledgeSource(name: string): Promise<void> {
  try {
    await db.deleteDoc(doctype['Knowledge Source'], name);
  } catch (error) {
    handleFrappeError(error, `Error deleting knowledge source ${name}`);
  }
}

// ---------------------------------------------------------------------------
// Knowledge Source actions
// ---------------------------------------------------------------------------

export async function rebuildIndex(
  knowledgeSource: string,
): Promise<{ status: string; message: string }> {
  try {
    const result = await call.post(
      'huf.huf.doctype.knowledge_source.knowledge_source.rebuild_index',
      { knowledge_source: knowledgeSource },
    );
    return (result as any).message ?? result;
  } catch (error) {
    handleFrappeError(error, 'Error rebuilding index');
  }
}

export async function testSearch(
  knowledgeSource: string,
  query: string,
  topK: number = 5,
): Promise<any> {
  try {
    const result = await call.post(
      'huf.huf.doctype.knowledge_source.knowledge_source.test_search',
      { knowledge_source: knowledgeSource, query, top_k: topK },
    );
    return (result as any).message ?? result;
  } catch (error) {
    handleFrappeError(error, 'Error running test search');
  }
}

// ---------------------------------------------------------------------------
// Knowledge Input
// ---------------------------------------------------------------------------

const KNOWLEDGE_INPUT_LIST_FIELDS = [
  'name',
  'knowledge_source',
  'input_type',
  'file',
  'file_name',
  'file_type',
  'text',
  'url',
  'status',
  'chunks_created',
  'character_count',
  'processed_at',
  'error_message',
];

export async function getKnowledgeInputs(
  knowledgeSource: string,
): Promise<KnowledgeInputDoc[]> {
  try {
    const inputs = await db.getDocList(doctype['Knowledge Input'], {
      fields: KNOWLEDGE_INPUT_LIST_FIELDS,
      filters: [['knowledge_source', '=', knowledgeSource]],
      limit: 1000,
      orderBy: { field: 'modified', order: 'desc' },
    });
    return inputs as KnowledgeInputDoc[];
  } catch (error) {
    handleFrappeError(error, 'Error fetching knowledge inputs');
  }
}

export async function createKnowledgeInput(
  data: Partial<KnowledgeInputDoc>,
): Promise<KnowledgeInputDoc> {
  try {
    const doc = await db.createDoc(doctype['Knowledge Input'], data);
    return doc as KnowledgeInputDoc;
  } catch (error) {
    handleFrappeError(error, 'Error creating knowledge input');
  }
}

export async function deleteKnowledgeInput(name: string): Promise<void> {
  try {
    await db.deleteDoc(doctype['Knowledge Input'], name);
  } catch (error) {
    handleFrappeError(error, `Error deleting knowledge input ${name}`);
  }
}

export async function reprocessInput(knowledgeInput: string): Promise<void> {
  try {
    await call.post(
      'huf.huf.doctype.knowledge_input.knowledge_input.reprocess_input',
      { knowledge_input: knowledgeInput },
    );
  } catch (error) {
    handleFrappeError(error, 'Error reprocessing knowledge input');
  }
}
