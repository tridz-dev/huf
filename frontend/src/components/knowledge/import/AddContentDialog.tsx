import { useEffect, useMemo, useState, type DragEvent } from 'react';
import { Cloud, FolderOpen, Loader2, Server, ChevronLeft } from 'lucide-react';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { Dialog, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import {
  DialogScrollBody,
  DialogScrollContent,
  DialogScrollFooter,
  DialogScrollHeader,
} from '@/components/ui/dialog-scroll';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { file as frappeFile } from '@/lib/frappe-sdk';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import {
  createKnowledgeInput,
  getImportOptions,
  knowledgeInputHasTitle,
  startImport,
  type ImportConfig,
  type ImportOptions,
  type SourceKind,
} from '@/services/knowledgeApi';
import type { KnowledgeInputDoc } from '@/types/knowledge.types';
import { UploadPanel } from './UploadPanel';
import { MAX_FILE_MB, EMPTY_REMOTE, isZip, stageFiles, type RemoteValues, type StagedFile } from './importHelpers';
import { EMPTY_DIRECT, TextPanel, WebPagePanel, type DirectValues } from './DirectInputPanels';
import { DirectoryPanel, S3Panel, SftpPanel } from './RemoteSourcePanels';

type Primary = 'upload' | 'url' | 'text' | 'storage';
type StorageKind = 'directory' | 's3' | 'sftp';
type TabKey = Primary | StorageKind;

interface AddContentDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  knowledgeSource: string;
  sourceLabel?: string;
  onStarted: (ingestion: string) => void;
  /** Called after a Text or Web page input is created directly (no ingestion). */
  onInputAdded?: () => void;
  /** When set, shows a "Skip for now" link (used by the create flow). */
  onSkip?: () => void;
  /** Open preselected on a choice. */
  initialTab?: 'upload' | 'storage';
  /** Files to stage as soon as the dialog opens (dropped on the page). */
  initialFiles?: File[];
}

async function uploadPrivate(file: File, onProgress: (pct: number) => void): Promise<string> {
  const response = await frappeFile.uploadFile(
    file,
    { isPrivate: true, doctype: 'Knowledge Source' },
    (completed, total) => {
      if (total) onProgress(Math.round((completed / total) * 100));
    },
  );
  const res = response as { data?: { message?: { name?: string } } };
  const name = res?.data?.message?.name;
  if (!name) throw new Error(`Could not upload ${file.name}`);
  return name;
}

export function AddContentDialog({
  open,
  onOpenChange,
  knowledgeSource,
  sourceLabel,
  onStarted,
  onInputAdded,
  onSkip,
  initialTab = 'upload',
  initialFiles,
}: AddContentDialogProps) {
  const [options, setOptions] = useState<ImportOptions | null>(null);
  const [optionsError, setOptionsError] = useState<string | null>(null);
  const [primary, setPrimary] = useState<Primary>(initialTab);
  const [storageKind, setStorageKind] = useState<StorageKind | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const tab: TabKey = primary === 'storage' ? storageKind ?? 'storage' : primary;
  const [staged, setStaged] = useState<StagedFile[]>([]);
  const [remote, setRemote] = useState<RemoteValues>(EMPTY_REMOTE);
  const [direct, setDirect] = useState<DirectValues>(EMPTY_DIRECT);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setError(null);
    setOptionsError(null);
    getImportOptions(knowledgeSource)
      .then(setOptions)
      .catch((e) => setOptionsError(getFrappeErrorMessage(e) || 'Could not load import options'));
  }, [open, knowledgeSource]);

  useEffect(() => {
    if (!open) {
      setStaged([]);
      setRemote(EMPTY_REMOTE);
      setDirect(EMPTY_DIRECT);
      setPrimary('upload');
      setStorageKind(null);
      setDragOver(false);
      setBusy(false);
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    setPrimary(initialTab);
    if (initialFiles && initialFiles.length > 0 && options) {
      setPrimary('upload');
      setStaged((cur) => [...cur, ...stageFiles(initialFiles, options.allowed_extensions, cur)]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, initialFiles, options]);

  const kinds = useMemo(() => new Set<SourceKind>(options?.source_kinds ?? []), [options]);
  const accepted = staged.filter((s) => !s.rejected);

  const canSubmit =
    !busy &&
    ((tab === 'upload' && accepted.length > 0) ||
      (tab === 'text' && direct.text.trim().length > 0) ||
      (tab === 'url' && direct.url.trim().length > 0) ||
      (tab === 'directory' && remote.dirPath.trim().length > 0) ||
      (tab === 's3' && !!options?.s3_configured && remote.bucket.trim().length > 0) ||
      (tab === 'sftp' && !!remote.sshConnection && remote.rootPath.trim().length > 0));

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      if (tab === 'text' || tab === 'url') {
        const data: Partial<KnowledgeInputDoc> = { knowledge_source: knowledgeSource };
        if (tab === 'text') {
          data.input_type = 'Text';
          data.text = direct.text;
          // Only send title once the doctype has the field (needs a migrate).
          if (direct.title.trim() && (await knowledgeInputHasTitle())) data.title = direct.title.trim();
        } else {
          data.input_type = 'URL';
          data.url = direct.url.trim();
        }
        await createKnowledgeInput(data);
        toast.success(tab === 'text' ? 'Text added. We are indexing it now.' : 'Web page added. We are reading it now.');
        onOpenChange(false);
        onInputAdded?.();
        return;
      }
      let kind: SourceKind;
      let config: ImportConfig;
      if (tab === 'upload') {
        const names: string[] = [];
        for (const s of accepted) {
          setStaged((list) => list.map((x) => (x.id === s.id ? { ...x, progress: 0 } : x)));
          const name = await uploadPrivate(s.file, (pct) =>
            setStaged((list) => list.map((x) => (x.id === s.id ? { ...x, progress: pct } : x))),
          );
          setStaged((list) => list.map((x) => (x.id === s.id ? { ...x, progress: 100 } : x)));
          names.push(name);
        }
        if (accepted.length === 1 && isZip(accepted[0].file)) {
          kind = 'Zip';
          config = { file: names[0] };
        } else {
          kind = 'Upload';
          config = { files: names };
        }
      } else if (tab === 'directory') {
        kind = 'Directory';
        config = { path: remote.dirPath.trim() };
      } else if (tab === 's3') {
        kind = 'S3';
        config = { bucket: remote.bucket.trim(), prefix: remote.prefix.trim() };
      } else {
        kind = 'SFTP';
        config = { ssh_connection: remote.sshConnection, root_path: remote.rootPath.trim() };
      }
      const result = await startImport(knowledgeSource, kind, config);
      onOpenChange(false);
      onStarted(result.ingestion);
    } catch (e) {
      setError(getFrappeErrorMessage(e) || 'We could not start the import. Please try again.');
      setStaged((list) => list.map((x) => ({ ...x, progress: undefined })));
    } finally {
      setBusy(false);
    }
  };

  const storageCards: Array<{ key: StorageKind; title: string; text: string; icon: typeof Cloud; show: boolean }> = [
    { key: 's3', title: 'Amazon S3 / Cloudflare R2', text: 'Import everything under a bucket folder.', icon: Cloud, show: kinds.has('S3') },
    { key: 'sftp', title: 'SFTP server', text: 'Import files from a server you have connected.', icon: Server, show: kinds.has('SFTP') },
    { key: 'directory', title: 'Server folder', text: 'Import from a folder on this server.', icon: FolderOpen, show: kinds.has('Directory') },
  ];
  const visibleCards = storageCards.filter((c) => c.show);
  const primaries: Array<{ key: Primary; label: string; show: boolean }> = [
    { key: 'upload', label: 'Upload files', show: true },
    { key: 'url', label: 'Web page', show: true },
    { key: 'text', label: 'Text', show: true },
    { key: 'storage', label: 'Connect storage', show: visibleCards.length > 0 },
  ];
  const maxMb = options?.max_file_mb ?? MAX_FILE_MB;

  const submitLabel =
    tab === 'upload' ? (accepted.length > 0 ? `Add ${accepted.length} ${accepted.length === 1 ? 'file' : 'files'}` : 'Add files')
    : tab === 'url' ? 'Add web page'
    : tab === 'text' ? 'Add text'
    : 'Start import';
  const disabledReason = busy
    ? ''
    : tab === 'upload' ? 'Choose at least one file first.'
    : tab === 'url' ? 'Enter a web address first.'
    : tab === 'text' ? 'Type or paste some text first.'
    : tab === 'storage' ? 'Choose where to import from.'
    : 'Fill in the required fields first.';

  const onDropBody = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragOver(false);
    if (busy || !options || e.dataTransfer.files.length === 0) return;
    const dropped = Array.from(e.dataTransfer.files);
    setPrimary('upload');
    setStaged((cur) => [...cur, ...stageFiles(dropped, options.allowed_extensions, cur)]);
  };

  return (
    <Dialog open={open} onOpenChange={(next) => (busy ? undefined : onOpenChange(next))}>
      <DialogScrollContent className="max-w-2xl">
        <DialogScrollHeader>
          <DialogTitle>Add content{sourceLabel ? ` to "${sourceLabel}"` : ''}</DialogTitle>
          <DialogDescription>
            Add documents so your agents can answer from them. We read and prepare them in the background.
          </DialogDescription>
        </DialogScrollHeader>
        <DialogScrollBody
          className={cn('space-y-4 py-2 transition-colors', dragOver && 'rounded-md bg-primary/5 ring-2 ring-primary ring-offset-2')}
          onDragOver={(e: DragEvent<HTMLDivElement>) => {
            e.preventDefault();
            if (!busy) setDragOver(true);
          }}
          onDragLeave={(e: DragEvent<HTMLDivElement>) => {
            if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragOver(false);
          }}
          onDrop={onDropBody}
          data-testid="add-content-body"
        >
          {optionsError && (
            <Alert variant="destructive">
              <AlertDescription>{optionsError}</AlertDescription>
            </Alert>
          )}
          {!options && !optionsError && (
            <div className="flex justify-center py-8">
              <Loader2 className="h-5 w-5 animate-spin text-steel-soft" />
            </div>
          )}
          {options && (
            <Tabs value={primary} onValueChange={(v) => setPrimary(v as Primary)}>
              <TabsList className="w-full">
                {primaries.filter((t) => t.show).map((t) => (
                  <TabsTrigger key={t.key} value={t.key} disabled={busy} className="flex-1">
                    {t.label}
                  </TabsTrigger>
                ))}
              </TabsList>
              <TabsContent value="upload" className="pt-3">
                <UploadPanel
                  staged={staged}
                  allowedExtensions={options.allowed_extensions}
                  maxMb={maxMb}
                  disabled={busy}
                  onChange={setStaged}
                />
              </TabsContent>
              <TabsContent value="url" className="pt-3">
                <WebPagePanel values={direct} onChange={setDirect} disabled={busy} />
              </TabsContent>
              <TabsContent value="text" className="pt-3">
                <TextPanel values={direct} onChange={setDirect} disabled={busy} />
              </TabsContent>
              <TabsContent value="storage" className="pt-3">
                {storageKind === null ? (
                  <div className="grid gap-2">
                    {visibleCards.map((c) => (
                      <button
                        key={c.key}
                        type="button"
                        disabled={busy}
                        onClick={() => setStorageKind(c.key)}
                        className="flex items-center gap-3 rounded-md border p-3 text-left hover:bg-muted"
                        data-testid={`storage-card-${c.key}`}
                      >
                        <c.icon className="h-5 w-5 shrink-0 text-steel-soft" />
                        <span>
                          <span className="block text-sm font-medium">{c.title}</span>
                          <span className="block text-xs text-steel">{c.text}</span>
                        </span>
                      </button>
                    ))}
                  </div>
                ) : (
                  <div className="space-y-3">
                    <Button type="button" variant="ghost" size="sm" onClick={() => setStorageKind(null)} disabled={busy}>
                      <ChevronLeft className="mr-1 h-4 w-4" />
                      Back
                    </Button>
                    {storageKind === 'directory' && <DirectoryPanel options={options} values={remote} onChange={setRemote} disabled={busy} />}
                    {storageKind === 's3' && <S3Panel options={options} values={remote} onChange={setRemote} disabled={busy} />}
                    {storageKind === 'sftp' && <SftpPanel options={options} values={remote} onChange={setRemote} disabled={busy} />}
                  </div>
                )}
              </TabsContent>
            </Tabs>
          )}
          {error && (
            <Alert variant="destructive" data-testid="import-error">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
        </DialogScrollBody>
        <DialogScrollFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => (onSkip ? onSkip() : onOpenChange(false))}
            disabled={busy}
          >
            {onSkip ? 'Skip for now' : 'Cancel'}
          </Button>
          <Tooltip>
            <TooltipTrigger asChild>
              <span tabIndex={canSubmit ? -1 : 0}>
                <Button type="button" onClick={() => void submit()} disabled={!canSubmit} data-testid="import-submit">
                  {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  {submitLabel}
                </Button>
              </span>
            </TooltipTrigger>
            {!canSubmit && disabledReason && <TooltipContent>{disabledReason}</TooltipContent>}
          </Tooltip>
        </DialogScrollFooter>
      </DialogScrollContent>
    </Dialog>
  );
}
