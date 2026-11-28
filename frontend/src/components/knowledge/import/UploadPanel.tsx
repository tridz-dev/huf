import { useRef, useState } from 'react';
import { FileArchive, FileText, Upload, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';
import { MAX_FILE_MB, formatSize, isZip, stageFiles, type StagedFile } from './importHelpers';

interface UploadPanelProps {
  staged: StagedFile[];
  allowedExtensions: string[];
  maxMb?: number;
  disabled?: boolean;
  onChange: (next: StagedFile[]) => void;
}

export function UploadPanel({ staged, allowedExtensions, maxMb = MAX_FILE_MB, disabled, onChange }: UploadPanelProps) {
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const add = (list: FileList | File[] | null) => {
    if (!list || list.length === 0 || disabled) return;
    onChange([...staged, ...stageFiles(Array.from(list), allowedExtensions, staged)]);
  };

  return (
    <div className="space-y-3">
      <div
        data-testid="upload-dropzone"
        className={cn(
          'flex cursor-pointer flex-col items-center justify-center gap-2 rounded-md border border-dashed p-8 text-center transition-colors',
          dragOver ? 'border-primary bg-primary/5' : 'border-input',
          disabled && 'pointer-events-none opacity-60',
        )}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          add(e.dataTransfer.files);
        }}
      >
        <Upload className="h-6 w-6 text-steel-soft" />
        <p className="text-sm">
          Drop files anywhere here, or <span className="text-signal-ink underline">choose files</span>
        </p>
        <p className="text-xs text-steel-soft">
          PDF, Word, PowerPoint, Excel, CSV, text, Markdown or web pages · up to {maxMb} MB each · a .zip is unpacked
        </p>
        <Input
          ref={inputRef}
          type="file"
          multiple
          className="hidden"
          data-testid="upload-input"
          onChange={(e) => {
            add(e.target.files);
            e.target.value = '';
          }}
        />
      </div>

      {staged.length > 0 && (
        <ul className="max-h-56 space-y-2 overflow-auto">
          {staged.map((s) => {
            const Icon = isZip(s.file) ? FileArchive : FileText;
            return (
              <li key={s.id} className="flex items-center gap-3 rounded-md border p-2.5">
                <Icon className="h-4 w-4 flex-shrink-0 text-steel-soft" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm">{s.file.name}</p>
                  {s.rejected ? (
                    <p className="text-xs text-destructive">{s.rejected}</p>
                  ) : s.progress !== undefined ? (
                    <Progress value={s.progress} className="mt-1 h-1" />
                  ) : (
                    <p className="text-xs text-steel-soft">
                      {formatSize(s.file.size)}
                      {isZip(s.file) ? ', will be unpacked' : ''}
                    </p>
                  )}
                </div>
                {!disabled && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`Remove ${s.file.name}`}
                    onClick={() => onChange(staged.filter((x) => x.id !== s.id))}
                  >
                    <X className="h-3.5 w-3.5" />
                  </Button>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
