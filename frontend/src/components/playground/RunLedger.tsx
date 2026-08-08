import { Star } from 'lucide-react';
import { StatusDot } from '@/components/dashboard';
import { cn } from '@/lib/utils';
import type { LedgerEntry } from './ledgerStorage';

export interface RunLedgerProps {
  entries: LedgerEntry[];
  /** Id of the most recently added entry — gets the drop-in animation. */
  latestEntryId?: string;
  onRestore: (entry: LedgerEntry) => void;
  onSaveAsTemplate: (entry: LedgerEntry) => void;
}

function formatTime(ranAt: number): string {
  return new Date(ranAt).toLocaleTimeString('en-GB', { hour12: false });
}

export function RunLedger({ entries, latestEntryId, onRestore, onSaveAsTemplate }: RunLedgerProps) {
  return (
    <div className="rounded border border-line bg-panel">
      <div className="border-b border-line px-3.5 py-2.5 font-display text-[14px] font-bold uppercase">
        Run ledger
      </div>

      {entries.length === 0 ? (
        <p className="px-3.5 py-3 text-[12.5px] text-steel-soft">
          No runs yet — completed runs are recorded here.
        </p>
      ) : (
        <div className="max-h-[220px] overflow-y-auto font-mono text-[12px]">
          {entries.map((entry) => (
            <div
              key={entry.id}
              role="button"
              tabIndex={0}
              onClick={() => onRestore(entry)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  onRestore(entry);
                }
              }}
              title="Restore this run's config and prompt"
              className={cn(
                'grid cursor-pointer grid-cols-[90px_1fr_70px_70px_70px_24px] items-center gap-2.5 border-b border-dashed border-line px-3.5 py-[9px] transition-colors last:border-b-0 hover:bg-paper-deep',
                entry.id === latestEntryId && 'animate-drop motion-reduce:animate-none',
              )}
            >
              <span className="text-steel">{formatTime(entry.ranAt)}</span>
              <span className="truncate text-ink">{entry.model || '—'}</span>
              <span className="text-steel">
                {entry.latencyMs !== undefined ? `${(entry.latencyMs / 1000).toFixed(1)}s` : '—'}
              </span>
              <span className="text-steel">
                {entry.tokens !== undefined ? `${entry.tokens} tok` : '—'}
              </span>
              <span
                className={cn(
                  'flex items-center gap-1.5',
                  entry.status === 'ok' ? 'text-good' : 'text-signal-ink',
                )}
              >
                <StatusDot variant={entry.status === 'ok' ? 'ok' : 'fail'} />
                {entry.status}
              </span>
              <button
                type="button"
                aria-label="Save prompt as template"
                title="Save prompt as template"
                onClick={(e) => {
                  e.stopPropagation();
                  onSaveAsTemplate(entry);
                }}
                className="justify-self-end text-steel-soft transition-colors hover:text-signal"
              >
                <Star className="h-3.5 w-3.5" strokeWidth={1.8} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
