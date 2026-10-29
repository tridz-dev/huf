import { useMemo, useState } from 'react';
import { Copy, ExternalLink, FileText, Image as ImageIcon, List, MapPin, Phone, Play, Reply } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { PreviewInput } from './templateModel';
import { FormattedText } from './preview/FormattedText';
import {
  inputToPreviewModel,
  PREVIEW_SAMPLES,
  type PreviewButtonType,
  type PreviewHeader,
  type PreviewModel,
  type PreviewSample,
} from './preview/previewModel';

export type { PreviewModel, PreviewSample } from './preview/previewModel';

const BUTTON_ICON = { QUICK_REPLY: Reply, URL: ExternalLink, PHONE_NUMBER: Phone, COPY_CODE: Copy } as const;
const COLLAPSE_ABOVE = 3;

const WALLPAPER = {
  backgroundImage: 'radial-gradient(var(--line) 1px, transparent 1px)',
  backgroundSize: '14px 14px',
} as const;

function currentTime() {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

function MediaHeader({ header }: { header: Exclude<PreviewHeader, { kind: 'text' }> }) {
  const [failed, setFailed] = useState(false);
  const box = 'flex aspect-video w-full items-center justify-center bg-paper-deep text-steel';
  if (header.kind === 'image') {
    if (header.url && !failed) {
      return <img src={header.url} alt="" className="aspect-video w-full object-cover" onError={() => setFailed(true)} />;
    }
    return (
      <div className={box} data-testid="header-image">
        <ImageIcon className="h-8 w-8" />
      </div>
    );
  }
  if (header.kind === 'video') {
    return (
      <div className={box} data-testid="header-video">
        <span className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/60 text-primary-foreground">
          <Play className="h-5 w-5" />
        </span>
      </div>
    );
  }
  if (header.kind === 'document') {
    return (
      <div className="m-1 flex items-center gap-2 rounded-md bg-paper-deep px-3 py-3 text-steel" data-testid="header-document">
        <FileText className="h-6 w-6 shrink-0" />
        <span className="truncate text-xs">{header.filename || 'Document'}</span>
      </div>
    );
  }
  return (
    <div className={cn(box, 'flex-col gap-1')} data-testid="header-location">
      <MapPin className="h-8 w-8" />
      <span className="text-xs">Location</span>
    </div>
  );
}

function Buttons({ buttons }: { buttons: { type: PreviewButtonType; text: string }[] }) {
  const [expanded, setExpanded] = useState(false);
  const collapsed = buttons.length > COLLAPSE_ABOVE && !expanded;
  const visible = collapsed ? buttons.slice(0, 2) : buttons;
  const row =
    'flex w-full items-center justify-center gap-1.5 rounded-lg bg-panel px-3 py-2 text-sm font-medium text-signal-ink shadow-sm';
  return (
    <div className="mt-1 space-y-1">
      {visible.map((b, i) => {
        const Icon = BUTTON_ICON[b.type];
        return (
          <div key={i} className={row} data-testid="preview-button">
            <Icon className="h-3.5 w-3.5" />
            {b.text}
          </div>
        );
      })}
      {collapsed && (
        <button type="button" className={row} onClick={() => setExpanded(true)}>
          <List className="h-3.5 w-3.5" />
          See all options
        </button>
      )}
    </div>
  );
}

export interface TemplatePreviewProps {
  /** Existing wizard/list input; adapted to a PreviewModel. */
  input?: PreviewInput;
  /** Richer model; takes precedence over `input`. */
  model?: PreviewModel;
  /** Canned Meta wizard copy for the category step; takes precedence over `model` and `input`. */
  sample?: PreviewSample;
  /** Bubble timestamp, HH:MM. Defaults to the current time. */
  time?: string;
  className?: string;
}

/** A message bubble the way the customer will see it in WhatsApp. */
export function TemplatePreview({ input, model: modelProp, sample, time, className }: TemplatePreviewProps) {
  const model = useMemo(
    () => (sample ? PREVIEW_SAMPLES[sample] : (modelProp ?? (input ? inputToPreviewModel(input) : null))),
    [sample, modelProp, input],
  );
  const stamp = time ?? currentTime();
  const empty = !model || (!model.header && !model.body.trim() && !model.footer && model.buttons.length === 0);
  const header = model?.header;

  return (
    <div className={cn('rounded-md border border-line bg-paper-deep p-4', className)} style={WALLPAPER} aria-label="Message preview">
      {empty ? (
        <p className="py-6 text-center text-xs text-steel">Your message preview appears here as you type.</p>
      ) : (
        <div className="max-w-[320px]">
          <div className="overflow-hidden rounded-lg rounded-tl-none border border-line bg-panel shadow-sm">
            {header && header.kind !== 'text' && <MediaHeader header={header} />}
            <div className="space-y-1 px-3 py-2">
              {header?.kind === 'text' && (
                <FormattedText
                  text={header.text}
                  samples={header.sample ? [header.sample] : undefined}
                  className="whitespace-pre-wrap break-words text-base font-semibold text-ink"
                />
              )}
              {model.body.trim() && (
                <FormattedText text={model.body} samples={model.samples} className="whitespace-pre-wrap break-words text-sm text-ink" />
              )}
              {model.footer && <p dir="auto" className="break-words text-xs text-steel">{model.footer}</p>}
              <p className="text-right text-[11px] text-steel">{stamp}</p>
            </div>
          </div>
          {model.buttons.length > 0 && <Buttons buttons={model.buttons} />}
        </div>
      )}
    </div>
  );
}
