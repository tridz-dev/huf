export interface StagedFile {
  id: string;
  file: File;
  /** Client-side rejection reason; rejected files are never uploaded. */
  rejected?: string;
  /** 0-100 while uploading. */
  progress?: number;
}

export const MAX_FILE_MB = 50;

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function isZip(file: File): boolean {
  return file.name.toLowerCase().endsWith('.zip');
}

export function stageFiles(files: File[], allowedExtensions: string[], existing: StagedFile[]): StagedFile[] {
  const allowed = new Set(allowedExtensions.map((e) => e.replace(/^\./, '').toLowerCase()));
  allowed.add('zip');
  const seen = new Set(existing.map((s) => `${s.file.name}:${s.file.size}`));
  const out: StagedFile[] = [];
  for (const file of files) {
    const key = `${file.name}:${file.size}`;
    if (seen.has(key)) continue;
    seen.add(key);
    const ext = file.name.includes('.') ? file.name.split('.').pop()!.toLowerCase() : '';
    let rejected: string | undefined;
    if (allowed.size > 1 && !allowed.has(ext)) rejected = 'This file type is not supported.';
    else if (!isZip(file) && file.size > MAX_FILE_MB * 1024 * 1024) rejected = `Larger than ${MAX_FILE_MB} MB.`;
    out.push({ id: `${key}-${Math.random().toString(36).slice(2)}`, file, rejected });
  }
  return out;
}


export interface RemoteValues {
  dirPath: string;
  bucket: string;
  prefix: string;
  sshConnection: string;
  rootPath: string;
}

export const EMPTY_REMOTE: RemoteValues = { dirPath: '', bucket: '', prefix: '', sshConnection: '', rootPath: '/' };

