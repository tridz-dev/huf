/**
 * TryPanel (DESIGN.md §6.12.7): a generic conversational test shell for the
 * side slot of a BuilderLayout. Head (title + draft badge + Reset), an
 * optional coaching banner, a message log with per-reply inspector rows
 * (tool calls, sources read, latency, tokens), an empty state with
 * suggestions, and a composer (Enter sends, Shift+Enter new line).
 * It renders what it is given; running the conversation is the caller's job.
 */
import { useEffect, useRef, type KeyboardEvent, type ReactNode } from 'react';
import { RotateCcw } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Spinner } from '@/components/ui/spinner';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';

export interface InspectorItem {
  /** `call` = an action it ran, `source` = something it read, `metric` = latency / tokens. */
  kind: 'call' | 'source' | 'metric';
  label: string;
  detail?: string;
  failed?: boolean;
}

export interface TryMessage {
  id: string;
  from: 'user' | 'reply';
  content: ReactNode;
  /** Reply still running; `content` is the step in progress ("Looking up order 1042…"). */
  pending?: boolean;
  inspector?: InspectorItem[];
}

export interface TryPanelProps {
  title?: string;
  /** e.g. "Draft · not published". */
  badge?: string;
  onReset?: () => void;
  messages: TryMessage[];
  /** Coaching / warning banner above the log (an AttentionBanner or similar). */
  banner?: ReactNode;
  /** Shown when there are no messages, e.g. TemplateChips of suggestions. */
  empty?: ReactNode;
  draft: string;
  onDraftChange: (v: string) => void;
  onSend: () => void;
  busy?: boolean;
  placeholder?: string;
  /** Under the composer: model line, "View run details". */
  footer?: ReactNode;
  className?: string;
}

const CHIP: Record<InspectorItem['kind'], string> = {
  call: 'bg-paper-deep text-ink',
  source: 'bg-signal/10 text-signal-ink',
  metric: 'bg-transparent text-steel font-mono',
};

export function Inspector({ items }: { items: InspectorItem[] }) {
  return (
    <ul aria-label="Run details" className="mt-2 flex flex-wrap gap-1.5">
      {items.map((it, i) => (
        <li key={`${it.kind}-${i}`} title={it.detail}
          className={cn('rounded-full px-2 py-0.5 text-meta', it.failed ? 'bg-destructive-tint text-destructive' : CHIP[it.kind])}>
          {it.kind === 'source' ? `Read: ${it.label}` : it.label}
        </li>
      ))}
    </ul>
  );
}

export function TryPanel({
  title = 'Try it', badge, onReset, messages, banner, empty, draft, onDraftChange, onSend, busy, placeholder = 'Type a message…', footer, className,
}: TryPanelProps) {
  const log = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = log.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);
  const send = () => {
    if (draft.trim() && !busy) onSend();
  };
  const onKey = (e: KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      send();
    }
  };
  return (
    <div className={cn('flex h-full min-h-96 flex-col overflow-hidden rounded-lg border border-line bg-panel', className)}>
      <div className="flex items-center gap-2 border-b border-line px-4 py-3">
        <h2 className="text-ui-text font-semibold text-ink">{title}</h2>
        {badge && <Badge variant="pill-neutral">{badge}</Badge>}
        {onReset && (
          <Button size="sm" variant="outline" className="ml-auto gap-1.5" onClick={onReset}>
            <RotateCcw aria-hidden="true" className="h-3.5 w-3.5" /> Reset
          </Button>
        )}
      </div>
      {banner && <div className="border-b border-line">{banner}</div>}
      <div ref={log} role="log" aria-live="polite" aria-label={`${title} conversation`} className="flex-1 space-y-3 overflow-y-auto p-4">
        {messages.length === 0 && empty}
        {messages.map((m) => (
          <div key={m.id} className={cn('flex', m.from === 'user' ? 'justify-end' : 'justify-start')}>
            <div aria-busy={m.pending || undefined}
              className={cn('max-w-[85%] rounded-xl px-3.5 py-2.5 text-ui-text', m.from === 'user' ? 'bg-ink text-primary-foreground' : 'bg-paper-deep text-ink')}>
              {m.pending ? <span className="inline-flex items-center gap-2"><Spinner role="presentation" aria-hidden="true" className="h-3.5 w-3.5" />{m.content}</span> : m.content}
              {m.inspector && m.inspector.length > 0 && <Inspector items={m.inspector} />}
            </div>
          </div>
        ))}
      </div>
      <div className="border-t border-line p-3">
        <div className="flex items-end gap-2 rounded-lg border border-line bg-panel p-1.5 focus-within:ring-2 focus-within:ring-ring">
          <Textarea value={draft} onChange={(e) => onDraftChange(e.target.value)} onKeyDown={onKey} rows={1} placeholder={placeholder}
            aria-label="Message" className="max-h-32 min-h-0 flex-1 resize-none border-0 shadow-none focus-visible:ring-0" />
          <Button size="sm" onClick={send} disabled={!draft.trim() || busy}>Send</Button>
        </div>
        {footer && <div className="mt-2 flex items-center justify-between gap-2 text-micro text-steel">{footer}</div>}
      </div>
    </div>
  );
}
