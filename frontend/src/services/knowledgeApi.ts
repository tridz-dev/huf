import type { Filter } from 'frappe-js-sdk/lib/db/types';
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
  'last_indexed_at', 'modified',
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
      filters: filters.length > 0 ? (filters as Filter<Record<string, unknown>>[]) : undefined,
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
    let targetName = name;
    if (
      data.source_name &&
      typeof data.source_name === 'string' &&
      data.source_name.trim() &&
      data.source_name !== name
    ) {
      await db.renameDoc(doctype['Knowledge Source'], name, data.source_name);
      targetName = data.source_name;
    }
    await db.updateDoc(doctype['Knowledge Source'], targetName, data);
    const updated = await db.getDoc(doctype['Knowledge Source'], targetName);
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
    const response = result as { message?: { status: string; message: string } } & {
      status: string;
      message: string;
    };
    return response.message ?? response;
  } catch (error) {
    handleFrappeError(error, 'Error rebuilding index');
  }
}

export async function testSearch(
  knowledgeSource: string,
  query: string,
  topK: number = 5,
): Promise<unknown> {
  try {
    const result = await call.post(
      'huf.huf.doctype.knowledge_source.knowledge_source.test_search',
      { knowledge_source: knowledgeSource, query, top_k: topK },
    );
    const response = result as { message?: unknown };
    return response.message ?? result;
  } catch (error) {
    handleFrappeError(error, 'Error running test search');
  }
}

export interface AdvancedConfigSchemaEntry {
  key: string;
  label: string;
  type: 'number' | 'text' | 'boolean' | 'select';
  default?: unknown;
  help_text?: string;
  options?: string[];
  min?: number;
  max?: number;
  visible_when?: Record<string, unknown>;
}

export async function getAdvancedConfigSchema(
  knowledgeType: string,
): Promise<AdvancedConfigSchemaEntry[]> {
  try {
    const result = await call.get(
      'huf.ai.knowledge.backends.get_advanced_config_schema',
      { knowledge_type: knowledgeType },
    );
    const response = result as { message?: unknown } | undefined;
    const payload = response?.message ?? response;
    return Array.isArray(payload) ? (payload as AdvancedConfigSchemaEntry[]) : [];
  } catch (error) {
    handleFrappeError(error, 'Error fetching advanced config schema');
  }
}

// ---------------------------------------------------------------------------
// Knowledge Input
// ---------------------------------------------------------------------------

const KNOWLEDGE_INPUT_LIST_FIELDS = [
  'name',
  'knowledge_source',
  'ingestion',
  'skip_reason',
  'external_key',
  'input_type',
  'file',
  'file_name', 'creation',
  'file_type',
  'text',
  'url',
  'status',
  'chunks_created',
  'character_count',
  'processed_at',
  'error_message',
];

let inputTitleSupport: Promise<boolean> | null = null;

/** True when the Knowledge Input doctype has the optional `title` field (needs a migrate). */
export function knowledgeInputHasTitle(): Promise<boolean> {
  if (!inputTitleSupport) {
    inputTitleSupport = call
      .get('frappe.desk.form.load.getdoctype', { doctype: doctype['Knowledge Input'] })
      .then((r: { docs?: Array<{ fields?: Array<{ fieldname: string }> }> }) =>
        !!r?.docs?.[0]?.fields?.some((f) => f.fieldname === 'title'),
      )
      .catch(() => false);
  }
  return inputTitleSupport;
}

export async function getKnowledgeInputs(
  knowledgeSource: string,
): Promise<KnowledgeInputDoc[]> {
  try {
    const hasTitle = await knowledgeInputHasTitle();
    const inputs = await db.getDocList(doctype['Knowledge Input'], {
      fields: hasTitle ? [...KNOWLEDGE_INPUT_LIST_FIELDS, 'title'] : KNOWLEDGE_INPUT_LIST_FIELDS,
      filters: [['knowledge_source', '=', knowledgeSource]],
      limit: 1000,
      orderBy: { field: 'modified', order: 'desc' },
    });
    return inputs as KnowledgeInputDoc[];
  } catch (error) {
    handleFrappeError(error, 'Error fetching knowledge inputs');
  }
}

/** Per-status input counts for a source, computed server-side (no row cap). */
export async function getKnowledgeInputStatusCounts(
  knowledgeSource: string,
): Promise<Array<{ status: string; count: number }>> {
  const rows = await db.getDocList(doctype['Knowledge Input'], {
    fields: ['status', { COUNT: '*', as: 'count' }] as never,
    filters: [['knowledge_source', '=', knowledgeSource]],
    groupBy: 'status',
    limit: 50,
  } as never);
  return (rows as unknown as Array<{ status: string; count: number | string }>).map((r) => ({
    status: r.status,
    count: Number(r.count) || 0,
  }));
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

// ---------------------------------------------------------------------------
// Bulk import (huf.ai.knowledge.bulk_sources_api and bulk_api)
// ---------------------------------------------------------------------------

const SOURCES_API = 'huf.ai.knowledge.bulk_sources_api';
const BULK_API = 'huf.ai.knowledge.bulk_api';

export type SourceKind = 'Upload' | 'Zip' | 'Directory' | 'S3' | 'SFTP';

export type IngestionStatus =
  | 'Scanning'
  | 'Queued'
  | 'Running'
  | 'Completed'
  | 'Completed with Errors'
  | 'Failed'
  | 'Cancelled';

export const ACTIVE_INGESTION_STATUSES: readonly string[] = ['Scanning', 'Queued', 'Running'];

export interface ImportOptions {
  source_kinds: SourceKind[];
  directory_roots: string[];
  ssh_connections: Array<{ name: string; label: string }>;
  s3_configured: boolean;
  max_files: number;
  allowed_extensions: string[];
}

export type ImportConfig =
  | { files: string[] }
  | { file: string }
  | { path: string }
  | { bucket: string; prefix: string }
  | { ssh_connection: string; root_path: string };

export interface StartImportResult {
  ingestion: string;
  status: string;
  source_kind: SourceKind;
}

export interface IngestionHeader {
  name: string;
  knowledge_source: string;
  status: IngestionStatus;
  total_items: number;
  submitted_by?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  error_message?: string | null;
  modified?: string;
  /** Not returned by older backends. */
  source_kind?: SourceKind | null;
  source_config?: Partial<{ bucket: string; prefix: string; ssh_connection: string; root_path: string; path: string }> | null;
}

export interface IngestionCounts {
  pending: number;
  processing: number;
  indexed: number;
  error: number;
  skipped: number;
  total: number;
}

export interface IngestionItem {
  name: string;
  external_key?: string | null;
  file_name?: string | null;
  title?: string | null;
  status: 'Pending' | 'Processing' | 'Indexed' | 'Error' | 'Skipped';
  chunks_created?: number;
  attempts?: number;
  error_message?: string | null;
  skip_reason?: string | null;
}

export interface IngestionStatusResult {
  ingestion: IngestionHeader;
  counts: IngestionCounts;
  /** Fraction between 0 and 1. */
  progress: number;
  chunks_written: number;
  items: IngestionItem[];
}

export interface GetIngestionStatusParams {
  includeItems?: boolean;
  itemStatus?: string;
  limit?: number;
  start?: number;
}

function messageOf<T>(result: unknown): T {
  const r = result as { message?: T } | undefined;
  return (r?.message ?? (result as T)) as T;
}

export async function getImportOptions(knowledgeSource: string): Promise<ImportOptions> {
  try {
    const result = await call.get(`${SOURCES_API}.get_import_options`, {
      knowledge_source: knowledgeSource,
    });
    return messageOf<ImportOptions>(result);
  } catch (error) {
    handleFrappeError(error, 'Error loading import options');
  }
}

export async function startImport(
  knowledgeSource: string,
  sourceKind: SourceKind,
  config: ImportConfig,
): Promise<StartImportResult> {
  try {
    const result = await call.post(`${SOURCES_API}.start_import`, {
      knowledge_source: knowledgeSource,
      source_kind: sourceKind,
      config,
    });
    return messageOf<StartImportResult>(result);
  } catch (error) {
    handleFrappeError(error, 'Error starting import');
  }
}

export async function getIngestionStatus(
  ingestion: string,
  params: GetIngestionStatusParams = {},
): Promise<IngestionStatusResult> {
  try {
    const { includeItems = false, itemStatus, limit = 50, start = 0 } = params;
    const result = await call.get(`${BULK_API}.get_ingestion_status`, {
      ingestion,
      include_items: includeItems ? 1 : 0,
      ...(itemStatus ? { item_status: itemStatus } : {}),
      limit,
      start,
    });
    return messageOf<IngestionStatusResult>(result);
  } catch (error) {
    handleFrappeError(error, 'Error loading import progress');
  }
}

export async function listIngestions(
  knowledgeSource: string,
  limit: number = 20,
): Promise<IngestionHeader[]> {
  try {
    const result = await call.get(`${BULK_API}.list_ingestions`, {
      knowledge_source: knowledgeSource,
      limit,
    });
    return messageOf<{ ingestions: IngestionHeader[] }>(result).ingestions ?? [];
  } catch (error) {
    handleFrappeError(error, 'Error loading imports');
  }
}

export async function retryIngestion(
  ingestion: string,
  onlyFailed: boolean = true,
): Promise<{ ingestion: string; status: string; rescheduled?: number }> {
  try {
    const result = await call.post(`${BULK_API}.retry_ingestion`, {
      ingestion,
      only_failed: onlyFailed ? 1 : 0,
    });
    return messageOf(result);
  } catch (error) {
    handleFrappeError(error, 'Error retrying import');
  }
}

export async function cancelIngestion(
  ingestion: string,
): Promise<{ ingestion: string; status: string }> {
  try {
    const result = await call.post(`${BULK_API}.cancel_ingestion`, { ingestion });
    return messageOf(result);
  } catch (error) {
    handleFrappeError(error, 'Error stopping import');
  }
}
