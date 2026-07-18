import { useEffect, useState } from 'react';
import { Loader2, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { getFileTypeInfo } from '@/utils/fileTypeUtils';

export interface ChatAttachmentCardProps {
  name: string;
  file?: File;
  previewUrl?: string;
  label?: string;
  status?: 'ready' | 'uploading' | 'error';
  error?: string;
  onRemove?: () => void;
  className?: string;
}

export function ChatAttachmentCard({
  name,
  file,
  previewUrl,
  label,
  status = 'ready',
  error,
  onRemove,
  className,
}: ChatAttachmentCardProps) {
  const typeInfo = getFileTypeInfo(file ?? name);
  const displayLabel = label ?? typeInfo.label;
  const { Icon, isImage } = typeInfo;

  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const thumbnailUrl = previewUrl ?? objectUrl;

  useEffect(() => {
    if (previewUrl || !file || !isImage) {
      return;
    }
    const url = URL.createObjectURL(file);
    setObjectUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file, isImage, previewUrl]);

  const showThumbnail = isImage && thumbnailUrl;

  return (
    <div
      className={cn(
        'flex items-center gap-3 rounded-lg border bg-muted/40 px-3 py-2 max-w-full',
        status === 'error' ? 'border-destructive' : 'border-zinc-200',
        status === 'uploading' && 'opacity-70',
        className
      )}
    >
      <div className="relative size-10 shrink-0">
        {showThumbnail ? (
          <img
            src={thumbnailUrl}
            alt={name}
            className="size-10 rounded-md object-cover"
          />
        ) : (
          <div className="flex size-10 items-center justify-center rounded-md bg-muted text-muted-foreground">
            <Icon className="size-5" />
          </div>
        )}
        {status === 'uploading' && (
          <div className="absolute inset-0 flex items-center justify-center rounded-md bg-background/60">
            <Loader2 className="size-4 animate-spin" />
          </div>
        )}
      </div>

      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{name}</p>
        <p className={cn('text-xs', status === 'error' ? 'text-destructive' : 'text-muted-foreground')}>
          {status === 'error' && error ? error : displayLabel}
        </p>
      </div>

      {onRemove && status !== 'uploading' && (
        <button
          type="button"
          onClick={onRemove}
          className="shrink-0 rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
          aria-label="Remove attachment"
        >
          <X className="size-4" />
        </button>
      )}
    </div>
  );
}
