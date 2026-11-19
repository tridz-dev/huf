import type { IngestionItem, IngestionStatus, SourceKind } from '@/services/knowledgeApi';
import type { KnowledgeInputDoc, KnowledgeSourceDoc } from '@/types/knowledge.types';

export const INGESTION_STATUS_LABELS: Record<string, string> = {
  Scanning: 'Looking for files',
  Queued: 'Waiting to start',
  Running: 'Reading and indexing',
  Completed: 'Done',
  'Completed with Errors': 'Done, some files need attention',
  Failed: 'Could not finish',
  Cancelled: 'Stopped',
};

export function ingestionStatusLabel(status: IngestionStatus | string): string {
  return INGESTION_STATUS_LABELS[status] ?? status;
}

export const SOURCE_KIND_LABELS: Record<SourceKind, string> = {
  Upload: 'uploaded files',
  Zip: 'a zip file',
  Directory: 'a server folder',
  S3: 'cloud storage (S3)',
  SFTP: 'an SFTP server',
};

const SKIP_REASON_TEXT: Record<string, string> = {
  'No Text': 'No readable text was found in this file.',
  Unsupported: 'This file type is not supported.',
  'Too Large': 'This file is larger than the size limit.',
  Duplicate: 'Same content as another file in this import.',
  Unchanged: 'Already added and has not changed.',
};

/** Plain-language reason for a skipped or failed item. Never shows raw internals. */
export function itemReason(item: Pick<IngestionItem, 'status' | 'skip_reason' | 'error_message'>): string {
  if (item.status === 'Skipped') {
    return (item.skip_reason && SKIP_REASON_TEXT[item.skip_reason]) || 'This file was skipped.';
  }
  if (item.status === 'Error') {
    const raw = (item.error_message || '').toLowerCase();
    if (raw.includes('worker died') || raw.includes('timed out') || raw.includes('timeout')) {
      return 'Processing was interrupted. Try again.';
    }
    if (raw.includes('modified after you have opened')) {
      return 'Processing was interrupted. Try again.';
    }
    if (raw.includes('fetch url') || raw.includes('404') || raw.includes('resolve')) {
      return 'We could not reach that address.';
    }
    return 'We could not read this file.';
  }
  return '';
}

export function itemStatusLabel(status: IngestionItem['status']): string {
  switch (status) {
    case 'Indexed':
      return 'Ready';
    case 'Error':
      return 'Failed';
    case 'Processing':
      return 'Indexing';
    case 'Pending':
      return 'Waiting';
    default:
      return status;
  }
}

export type HealthKey = 'ready' | 'updating' | 'attention' | 'empty' | 'broken' | 'paused';

export interface Health {
  key: HealthKey;
  label: string;
  hint: string;
}

export interface InputCounts {
  total: number;
  ready: number;
  failed: number;
  skipped: number;
  inProgress: number;
}

export function countInputs(inputs: Array<Pick<KnowledgeInputDoc, 'status'>>): InputCounts {
  const c: InputCounts = { total: inputs.length, ready: 0, failed: 0, skipped: 0, inProgress: 0 };
  for (const input of inputs) {
    const s = input.status as string;
    if (s === 'Indexed') c.ready += 1;
    else if (s === 'Error') c.failed += 1;
    else if (s === 'Skipped') c.skipped += 1;
    else c.inProgress += 1;
  }
  return c;
}

/** Plain-language health model computed client-side. */
export function computeHealth(
  source: Pick<KnowledgeSourceDoc, 'status' | 'disabled' | 'error_message'> | null,
  counts: InputCounts,
  hasActiveIngestion: boolean,
): Health {
  if (source?.disabled === 1) {
    return { key: 'paused', label: 'Paused', hint: 'Turned off. Agents cannot use it.' };
  }
  if (source?.status === 'Error') {
    return {
      key: 'broken',
      label: 'Not working',
      hint: 'Search is unavailable. Open Settings or try Rebuild search index.',
    };
  }
  if (hasActiveIngestion || counts.inProgress > 0 || source?.status === 'Indexing' || source?.status === 'Rebuilding') {
    return {
      key: 'updating',
      label: 'Updating',
      hint: 'Adding documents. You can still search what is ready.',
    };
  }
  if (counts.total === 0) {
    return { key: 'empty', label: 'Empty', hint: 'Add documents to get started.' };
  }
  if (counts.failed > 0) {
    return {
      key: 'attention',
      label: 'Needs attention',
      hint: `${counts.failed} ${counts.failed === 1 ? 'document' : 'documents'} could not be read.`,
    };
  }
  if (counts.ready > 0) {
    return { key: 'ready', label: 'Ready', hint: 'Agents can search this.' };
  }
  return { key: 'empty', label: 'Empty', hint: 'Add documents to get started.' };
}
