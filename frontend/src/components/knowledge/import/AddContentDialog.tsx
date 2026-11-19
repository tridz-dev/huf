import { useEffect, useMemo, useState } from 'react';
import { Loader2 } from 'lucide-react';
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
  getImportOptions,
  startImport,
  type ImportConfig,
  type ImportOptions,
  type SourceKind,
} from '@/services/knowledgeApi';
import { UploadPanel } from './UploadPanel';
import { EMPTY_REMOTE, isZip, type RemoteValues, type StagedFile } from './importHelpers';
import { DirectoryPanel, S3Panel, SftpPanel } from './RemoteSourcePanels';

type TabKey = 'upload' | 'directory' | 's3' | 'sftp';

interface AddContentDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  knowledgeSource: string;
  sourceLabel?: string;
  onStarted: (ingestion: string) => void;
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
}: AddContentDialogProps) {
  const [options, setOptions] = useState<ImportOptions | null>(null);
  const [optionsError, setOptionsError] = useState<string | null>(null);
  const [tab, setTab] = useState<TabKey>('upload');
  const [staged, setStaged] = useState<StagedFile[]>([]);
  const [remote, setRemote] = useState<RemoteValues>(EMPTY_REMOTE);
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
      setTab('upload');
      setBusy(false);
    }
  }, [open]);

  const kinds = useMemo(() => new Set<SourceKind>(options?.source_kinds ?? []), [options]);
  const accepted = staged.filter((s) => !s.rejected);

  const canSubmit =
    !busy &&
    ((tab === 'upload' && accepted.length > 0) ||
      (tab === 'directory' && remote.dirPath.trim().length > 0) ||
      (tab === 's3' && !!options?.s3_configured && remote.bucket.trim().length > 0) ||
      (tab === 'sftp' && !!remote.sshConnection && remote.rootPath.trim().length > 0));

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
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
      toast.success('Import started. You can keep working while we read your files.');
      onOpenChange(false);
      onStarted(result.ingestion);
    } catch (e) {
      setError(getFrappeErrorMessage(e) || 'We could not start the import. Please try again.');
      setStaged((list) => list.map((x) => ({ ...x, progress: undefined })));
    } finally {
      setBusy(false);
    }
  };

  const tabs: Array<{ key: TabKey; label: string; show: boolean }> = [
    { key: 'upload', label: 'Upload', show: true },
    { key: 'directory', label: 'Folder on server', show: kinds.has('Directory') },
    { key: 's3', label: 'S3', show: kinds.has('S3') },
    { key: 'sftp', label: 'SFTP', show: kinds.has('SFTP') },
  ];
  const visibleTabs = tabs.filter((t) => t.show);

  return (
    <Dialog open={open} onOpenChange={(next) => (busy ? undefined : onOpenChange(next))}>
      <DialogScrollContent className="max-w-2xl">
        <DialogScrollHeader>
          <DialogTitle>Add content{sourceLabel ? ` to "${sourceLabel}"` : ''}</DialogTitle>
          <DialogDescription>
            Add documents so your agents can answer from them. We read and prepare them in the background.
          </DialogDescription>
        </DialogScrollHeader>
        <DialogScrollBody className="space-y-4 py-2">
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
            <Tabs value={tab} onValueChange={(v) => setTab(v as TabKey)}>
              <TabsList>
                {visibleTabs.map((t) => (
                  <TabsTrigger key={t.key} value={t.key} disabled={busy}>
                    {t.label}
                  </TabsTrigger>
                ))}
              </TabsList>
              <TabsContent value="upload" className="pt-3">
                <UploadPanel
                  staged={staged}
                  allowedExtensions={options.allowed_extensions}
                  disabled={busy}
                  onChange={setStaged}
                />
              </TabsContent>
              <TabsContent value="directory" className="pt-3">
                <DirectoryPanel options={options} values={remote} onChange={setRemote} disabled={busy} />
              </TabsContent>
              <TabsContent value="s3" className="pt-3">
                <S3Panel options={options} values={remote} onChange={setRemote} disabled={busy} />
              </TabsContent>
              <TabsContent value="sftp" className="pt-3">
                <SftpPanel options={options} values={remote} onChange={setRemote} disabled={busy} />
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
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
          <Button type="button" onClick={() => void submit()} disabled={!canSubmit} data-testid="import-submit">
            {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {tab === 'upload' && accepted.length > 0
              ? `Import ${accepted.length} ${accepted.length === 1 ? 'item' : 'items'}`
              : 'Import'}
          </Button>
        </DialogScrollFooter>
      </DialogScrollContent>
    </Dialog>
  );
}
