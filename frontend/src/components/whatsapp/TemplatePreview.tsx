import { useMemo } from 'react';
import { ExternalLink, FileText, Image as ImageIcon, Phone, Reply } from 'lucide-react';
import { cn } from '@/lib/utils';
import { buildPreviewModel, type PreviewInput } from './templateModel';

const BUTTON_ICON = { QUICK_REPLY: Reply, URL: ExternalLink, PHONE_NUMBER: Phone } as const;

/** A message bubble the way the customer will see it in WhatsApp. */
export function TemplatePreview({ input, className }: { input: PreviewInput; className?: string }) {
  const model = useMemo(() => buildPreviewModel(input), [input]);
  const empty = !model.header && !model.body.trim() && !model.footer && model.buttons.length === 0;

  return (
    <div className={cn('rounded-md border border-line bg-paper-deep p-4', className)} aria-label="Message preview">
      {empty ? (
        <p className="py-6 text-center text-xs text-steel">Your message preview appears here as you type.</p>
      ) : (
        <div className="max-w-[320px]">
          <div className="overflow-hidden rounded-lg rounded-tl-none border border-line bg-panel shadow-sm">
            {model.header?.kind === 'media' && (
              <div className="flex h-32 items-center justify-center gap-2 bg-paper-deep text-steel">
                {model.header.media === 'IMAGE' ? <ImageIcon className="h-6 w-6" /> : <FileText className="h-6 w-6" />}
                <span className="text-xs">{model.header.media === 'IMAGE' ? 'Image' : 'Document'}</span>
              </div>
            )}
            <div className="space-y-1 px-3 py-2">
              {model.header?.kind === 'text' && <p className="text-sm font-semibold text-ink">{model.header.text}</p>}
              {model.body.trim() && <p className="whitespace-pre-wrap break-words text-sm text-ink">{model.body}</p>}
              {model.footer && <p className="text-xs text-steel">{model.footer}</p>}
            </div>
          </div>
          {model.buttons.length > 0 && (
            <div className="mt-1 space-y-1">
              {model.buttons.map((b, i) => {
                const Icon = BUTTON_ICON[b.type];
                return (
                  <div
                    key={i}
                    className="flex items-center justify-center gap-1.5 rounded-lg border border-line bg-panel px-3 py-2 text-sm font-medium text-ink"
                  >
                    <Icon className="h-3.5 w-3.5 text-steel" />
                    {b.text}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
