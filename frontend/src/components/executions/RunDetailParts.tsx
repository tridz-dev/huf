import { useState, type ReactNode } from 'react';
import { Copy, Check } from 'lucide-react';
import { cn } from '@/lib/utils';
import { copyText } from '@/lib/clipboard';

/** One row of the Overview / Tokens & Cost definition list. */
export function DefinitionRow({ label, value, mono }: { label: string; value: ReactNode; mono?: boolean }) {
  return (
    <div className="flex h-[26px] items-center justify-between gap-4">
      <span className="text-ui-text font-normal text-steel shrink-0">{label}</span>
      <span
        className={cn(
          'text-ui-text font-normal tabular-nums truncate text-right text-ink',
          mono && 'font-mono'
        )}
      >
        {value}
      </span>
    </div>
  );
}

/** A labeled column of DefinitionRows, headed by a mono uppercase eyebrow. */
export function DefinitionColumn({ heading, children }: { heading: string; children: ReactNode }) {
  return (
    <div>
      <div className="font-mono text-eyebrow uppercase tracking-widest text-steel pb-1.5">{heading}</div>
      <div className="divide-y divide-line">{children}</div>
    </div>
  );
}

/** One field in the Context panel's four-column stat row: 11px label over a 13px value. */
export function ContextStat({
  label,
  value,
  capitalize,
}: {
  label: string;
  value: ReactNode;
  capitalize?: boolean;
}) {
  return (
    <div className="min-w-0">
      <div className="text-meta text-steel truncate">{label}</div>
      <div className={cn('text-ui-text font-normal tabular-nums text-ink truncate', capitalize && 'capitalize')}>
        {value}
      </div>
    </div>
  );
}

/** Prompt/Response panel: title + copy button, content in a mono box. */
export function CopyableTextPanel({
  title,
  content,
  emptyText,
}: {
  title: string;
  content?: string | null;
  emptyText: string;
}) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    if (!content) return;
    try {
      if (!(await copyText(content))) throw new Error('Copy failed');
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch (error) {
      console.error('Failed to copy to clipboard:', error);
    }
  };

  return (
    <div className="rounded-lg border border-line bg-panel p-4">
      <div className="flex items-center justify-between gap-2 pb-2">
        <h3 className="text-ui-text font-normal font-[590] text-ink">{title}</h3>
        <button
          type="button"
          onClick={handleCopy}
          disabled={!content}
          aria-label={`Copy ${title.toLowerCase()}`}
          className="flex h-6 w-6 shrink-0 items-center justify-center rounded text-steel transition-colors hover:bg-paper-deep hover:text-ink disabled:pointer-events-none disabled:opacity-40"
        >
          {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
        </button>
      </div>
      <div className="max-h-[320px] overflow-auto whitespace-pre-wrap break-words rounded-md bg-paper-deep p-3 font-mono text-xs leading-[1.6] text-ink">
        {content || emptyText}
      </div>
    </div>
  );
}
