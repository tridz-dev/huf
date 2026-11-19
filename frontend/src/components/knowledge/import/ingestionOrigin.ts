import type { IngestionHeader, SourceKind } from '@/services/knowledgeApi';

const LABELS: Record<SourceKind, string> = {
  Upload: 'Upload',
  Zip: 'Zip file',
  Directory: 'Folder',
  S3: 'S3',
  SFTP: 'SFTP',
};

/** Plain-language source name; older backends send nothing, so default to Upload. */
export function ingestionSourceLabel(kind?: SourceKind | null): string {
  return (kind && LABELS[kind]) || 'Upload';
}

/** Short origin text (bucket/prefix, connection and path, or folder). Empty when unknown. */
export function ingestionOrigin(row: Pick<IngestionHeader, 'source_config'>): string {
  const c = row.source_config;
  if (!c || typeof c !== 'object') return '';
  const parts = [
    c.bucket ? `${c.bucket}${c.prefix ? `/${c.prefix.replace(/^\/+/, '')}` : ''}` : '',
    c.ssh_connection ? `${c.ssh_connection}${c.root_path ? `:${c.root_path}` : ''}` : '',
    !c.bucket && !c.ssh_connection ? c.path || c.root_path || '' : '',
  ].filter(Boolean);
  return parts.join(' · ');
}
