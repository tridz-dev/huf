import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { ArrowLeft, ChevronRight, Repeat, Search } from 'lucide-react';
import { Button } from '../../ui/button';
import { Input } from '../../ui/input';
import { cardIcon } from '../../nodes/nodeIcons';
import { cn } from '@/lib/utils';
import type { PickerModel, PickerStep } from '@/lib/flow-data/model';
import type { DataPick } from '@/lib/flow-data/types';
import { parentView, resolveTyped, searchRows, viewRows, viewTitle, type Accept, type PickerRow, type PickerView } from './pickerRows';

interface DataPickerProps {
  model: PickerModel;
  accept: Accept;
  onPick: (pick: DataPick) => void;
  /** Gets the last real request for the trigger and keeps it as the example. */
  /** Resolves to a sentence to show under the button when there is nothing to use yet. */
  onFetchLast: (step: PickerStep) => Promise<string | void>;
  loading?: boolean;
}

const SOURCE_WORDS = {
  pinned: 'Showing the example saved on this step',
  last_run: 'Showing real data from the last run',
  doctype: 'Showing a recent record',
  none: '',
} as const;

function StepIcon({ step }: { step: PickerStep }) {
  const Icon = step.kind === 'loop' ? Repeat : step.node ? cardIcon(step.node.data) : Search;
  return (
    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-muted text-foreground" aria-hidden>
      <Icon className="h-3.5 w-3.5" />
    </span>
  );
}

/**
 * The "Use data" picker: a step (by icon and title, the trigger first), then one of its fields by name with a real example.
 * A list offers "First item", "All items, joined with commas" and "How many items"; a thing with parts offers "Show as summary
 * table". Typing searches every field. Arrow keys move, Enter picks, Right opens, Left goes back; Esc closes (the popover).
 */
export function DataPicker({ model, accept, onPick, onFetchLast, loading }: DataPickerProps) {
  const [view, setView] = useState<PickerView>(() => (model.steps.length === 1 ? { kind: 'fields', stepId: model.steps[0].id } : { kind: 'steps' }));
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const [typing, setTyping] = useState(false);
  const [typed, setTyped] = useState('');
  const [fetching, setFetching] = useState(false);
  const [fetchNotice, setFetchNotice] = useState('');
  const searchRef = useRef<HTMLInputElement>(null);
  const listId = useId();

  const step = view.kind === 'steps' ? undefined : model.steps.find((s) => s.id === view.stepId);
  const rows = useMemo<PickerRow[]>(
    () => (query.trim() ? searchRows(model, query, accept, view.kind === 'steps' ? undefined : view.stepId) : viewRows(view, model, accept)),
    [model, view, query, accept]
  );
  const safeActive = Math.min(active, Math.max(rows.length - 1, 0));
  const firstEnabled = rows.findIndex((r) => !r.disabled);

  useEffect(() => {
    setActive(Math.max(firstEnabled, 0));
  }, [view, query, firstEnabled]);
  useEffect(() => {
    document.getElementById(`${listId}-${safeActive}`)?.scrollIntoView({ block: 'nearest' });
  }, [safeActive, listId]);

  const go = (next: PickerView) => {
    setView(next);
    setQuery('');
    setTyping(false);
    searchRef.current?.focus();
  };
  const run = (row: PickerRow | undefined) => {
    if (!row || row.disabled) return;
    if (row.action.type === 'view') go(row.action.view);
    else if (row.action.type === 'pick') onPick(row.action.pick);
  };
  const back = () => go(parentView(view));

  const onKeyDown = (e: React.KeyboardEvent) => {
    if ((e.target as HTMLElement).dataset.role === 'typed') return;
    const move = (d: number) => {
      e.preventDefault();
      let i = safeActive;
      for (let n = 0; n < rows.length; n++) {
        i = (i + d + rows.length) % rows.length;
        if (!rows[i].disabled) break;
      }
      setActive(i);
    };
    if (e.key === 'ArrowDown') move(1);
    else if (e.key === 'ArrowUp') move(-1);
    else if (e.key === 'Enter' && (e.target as HTMLElement).dataset.role !== 'typed') {
      e.preventDefault();
      run(rows[safeActive]);
    } else if (e.key === 'ArrowRight' && !query && rows[safeActive]?.chevron && e.target === searchRef.current) {
      e.preventDefault();
      run(rows[safeActive]);
    } else if ((e.key === 'ArrowLeft' || e.key === 'Backspace') && !query && view.kind !== 'steps') {
      e.preventDefault();
      back();
    }
  };

  const fetchLast = async () => {
    if (!step) return;
    setFetching(true);
    setFetchNotice('');
    try {
      const notice = await onFetchLast(step);
      setFetchNotice(typeof notice === 'string' ? notice : '');
    } finally {
      setFetching(false);
    }
  };

  const typedPick = resolveTyped(typed, model, step);
  const submitTyped = () => {
    if (typedPick) onPick(typedPick);
  };

  const showNoSample = Boolean(step && !query && view.kind === 'fields' && !step.hasSample && step.kind !== 'loop');

  return (
    <div role="dialog" aria-label="Use data" className="flex max-h-[min(440px,70vh)] flex-col" data-testid="flow-use-data" onKeyDown={onKeyDown}>
      <div className="flex items-center gap-1.5 border-b border-border p-2">
        {view.kind !== 'steps' ? (
          <Button type="button" variant="ghost" size="icon" className="shrink-0" onClick={back} aria-label="Back" data-testid="flow-use-data-back">
            <ArrowLeft className="h-4 w-4" aria-hidden />
          </Button>
        ) : null}
        <div className="min-w-0 flex-1 truncate text-ui-text font-medium" data-testid="flow-use-data-title">{viewTitle(view, model)}</div>
      </div>
      <div className="relative border-b border-border p-2">
        <Search className="pointer-events-none absolute left-4 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden />
        <Input
          ref={searchRef}
          autoFocus
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={view.kind === 'steps' ? 'Search steps and fields' : 'Search fields'}
          aria-label="Search the data you can use"
          aria-controls={listId}
          aria-activedescendant={rows.length ? `${listId}-${safeActive}` : undefined}
          className="pl-8"
          data-testid="flow-use-data-search"
        />
      </div>
      {step && view.kind === 'fields' && step.hasSample && !query ? (
        <p className="border-b border-border px-3 py-1.5 text-meta text-muted-foreground" data-testid="flow-use-data-source">
          {SOURCE_WORDS[step.source]}
        </p>
      ) : null}
      <div className="min-h-0 flex-1 overflow-y-auto p-1" role="listbox" id={listId} aria-label="Data you can use">
        {rows.map((r, i) => (
          <button
            key={r.key}
            type="button"
            role="option"
            id={`${listId}-${i}`}
            aria-selected={i === safeActive}
            aria-disabled={r.disabled || undefined}
            tabIndex={-1}
            data-testid={r.testId}
            onMouseMove={() => !r.disabled && setActive(i)}
            onClick={() => run(r)}
            className={cn(
              'flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left',
              i === safeActive && !r.disabled ? 'bg-accent' : '',
              r.disabled ? 'cursor-not-allowed opacity-60' : 'cursor-pointer'
            )}
          >
            {view.kind === 'steps' || (query && r.step) ? (r.step ? <StepIcon step={r.step} /> : null) : null}
            <span className="min-w-0 flex-1">
              <span className="block truncate text-ui-text">{r.title}</span>
              {r.subtitle ? <span className="block truncate text-meta text-muted-foreground">{r.subtitle}</span> : null}
            </span>
            {r.sample ? <span className="max-w-[45%] shrink-0 truncate text-meta text-muted-foreground" data-testid="flow-use-data-sample">{r.sample}</span> : null}
            {r.chevron ? <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden /> : null}
          </button>
        ))}
        {rows.length === 0 && !showNoSample ? (
          <p className="p-3 text-meta text-muted-foreground" data-testid="flow-use-data-empty">
            {query
              ? 'Nothing matches. Try a different word.'
              : model.steps.length === 0
                ? 'Nothing to pick from yet. Choose what starts this flow first.'
                : accept === 'list'
                  ? 'No list here yet. Run a test to see one.'
                  : 'No data here yet.'}
          </p>
        ) : null}
        {showNoSample && step ? (
          <div className="space-y-2 p-3" data-testid="flow-use-data-nosample">
            <p className="text-ui-text">No sample yet: run a test</p>
            <p className="text-meta text-muted-foreground">
              {step.canFetchLast
                ? 'Send your webhook a request, or use the last real one it received, to see its fields here.'
                : step.kind === 'trigger'
                  ? 'Run the flow once and the data it started with shows up here.'
                  : 'Run the flow once and what this step produced shows up here.'}
            </p>
            {step.canFetchLast ? (
              <Button type="button" size="sm" variant="outline" disabled={fetching} onClick={fetchLast} data-testid="flow-use-data-last-request">
                {fetching ? 'Looking…' : 'Use last real request'}
              </Button>
            ) : null}
            {fetchNotice ? <p className="text-meta text-muted-foreground" role="status" data-testid="flow-use-data-last-request-notice">{fetchNotice}</p> : null}
          </div>
        ) : null}
        {/* Never under "No sample yet": that answer is already final for this step, a loading line below it only flashes. */}
        {loading && !showNoSample ? <p className="p-2 text-meta text-muted-foreground" data-testid="flow-use-data-loading">Loading examples…</p> : null}
      </div>
      {view.kind === 'steps' || (step && view.kind === 'fields') ? (
        <div className="border-t border-border p-2">
          {typing ? (
            <div className="space-y-1">
              <Input
                autoFocus
                data-role="typed"
                value={typed}
                onChange={(e) => setTyped(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    submitTyped();
                  }
                }}
                placeholder="For example: customer.name"
                aria-label="Field name"
                data-testid="flow-use-data-typed"
              />
              <p className="text-meta text-muted-foreground">{typed && !typedPick ? (view.kind === 'steps' ? 'Start with the step, like input.customer.name.' : 'Use letters, numbers and dots, like customer.name.') : 'Type the name as it appears in the data, then press Enter.'}</p>
            </div>
          ) : (
            <Button type="button" variant="ghost" size="sm" className="w-full justify-start text-muted-foreground" onClick={() => setTyping(true)} data-testid="flow-use-data-type-it">
              Can&apos;t find it? Type the field name
            </Button>
          )}
        </div>
      ) : null}
    </div>
  );
}
