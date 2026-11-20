/**
 * AutosaveStatus (DESIGN.md §6.12.6): the quiet save indicator in a builder
 * head. "Unsaved changes" → "Saving…" → "Saved just now" / "Saved 4 min ago",
 * or "Couldn't save · Retry". A polite live region; only failure is coloured.
 */
import { useEffect, useState } from 'react';
import { AlertCircle, Check } from 'lucide-react';
import { Spinner } from '@/components/ui/spinner';
import { cn } from '@/lib/utils';

export type AutosaveState = 'idle' | 'dirty' | 'saving' | 'saved' | 'error';

export interface AutosaveStatusProps {
  state: AutosaveState;
  savedAt?: Date | number | null;
  onRetry?: () => void;
  /** Override the failure words, e.g. "Someone else changed this". */
  errorText?: string;
  /** Clock for tests. */
  now?: () => number;
  className?: string;
}

/** "just now" (< 1 min), "N min ago" (< 1 h), else the time of day. */
export function savedAgo(savedAt: Date | number, now: number): string {
  const t = typeof savedAt === 'number' ? savedAt : savedAt.getTime();
  const s = Math.max(0, (now - t) / 1000);
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  return `at ${new Date(t).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}`;
}

export function AutosaveStatus({ state, savedAt, onRetry, errorText = "Couldn't save", now = Date.now, className }: AutosaveStatusProps) {
  const [, tick] = useState(0);
  useEffect(() => {
    if (state !== 'saved') return;
    const id = window.setInterval(() => tick((n) => n + 1), 30_000);
    return () => window.clearInterval(id);
  }, [state]);

  let body: React.ReactNode = null;
  if (state === 'dirty') body = 'Unsaved changes';
  else if (state === 'saving') body = <><Spinner role="presentation" aria-hidden="true" className="h-3 w-3" /> Saving…</>;
  else if (state === 'saved') body = <><Check aria-hidden="true" className="h-3 w-3" /> Saved {savedAt ? savedAgo(savedAt, now()) : 'just now'}</>;
  else if (state === 'error') body = (
    <>
      <AlertCircle aria-hidden="true" className="h-3.5 w-3.5" /> {errorText}
      {onRetry && <> · <button type="button" onClick={onRetry} className="font-medium underline underline-offset-2 hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">Retry</button></>}
    </>
  );

  return (
    <span role="status" aria-live="polite" data-state={state} data-testid="autosave-status"
      className={cn('inline-flex items-center gap-1.5 text-micro', state === 'error' ? 'text-destructive' : 'text-steel', className)}>
      {body}
    </span>
  );
}
