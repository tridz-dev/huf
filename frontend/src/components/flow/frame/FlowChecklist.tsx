import { AlertCircle, ChevronDown } from 'lucide-react';
import { Button } from '../../ui/button';
import { Popover, PopoverAnchor, PopoverContent, PopoverTrigger } from '../../ui/popover';
import { useFlowContext } from '../../../contexts/FlowContext';
import { cn } from '@/lib/utils';
import { requestFocus, setChecklistOpen, useFrame } from './frameStore';
import { finishText, groupByStep } from './frameIssues';
import { useFlowIssues } from '@/hooks/flow/useFlowIssues';
import { useFrozenWhilePressed } from '@/hooks/flow/useFrozenWhilePressed';

/**
 * "3 steps to finish": opens the list of everything left to finish in the flow, each with a Fix button that selects
 * the step and puts the cursor in the field. Saving never waits for this list; Run and Publish open it instead of
 * failing quietly. `menuOnly` (a phone: the header has no room) draws no button; the list opens from the "..." menu and anchors here.
 */
export function FlowChecklist({ live, className, separator = true, menuOnly = false }: { live: boolean; className?: string; separator?: boolean; menuOnly?: boolean }) {
  const issues = useFlowIssues();
  const open = useFrame((s) => s.checklistOpen);
  const { setSelectedNode } = useFlowContext();
  const groups = groupByStep(issues);
  const text = finishText(issues);
  // Hold the header wording while a button is held down, so the controls beside it do not move under the pointer.
  const shownText = useFrozenWhilePressed(text);

  return (
    <Popover open={open && issues.length > 0} onOpenChange={setChecklistOpen}>
      <PopoverAnchor asChild>
        <span className={cn('inline-flex items-center gap-1.5', className)}>
          {shownText !== '' && !menuOnly && (
            <>
              {separator && <span aria-hidden className="text-muted-foreground/60">&middot;</span>}
              <PopoverTrigger asChild>
                <button
                  type="button"
                  data-testid="flow-validation-summary"
                  aria-label={`${shownText}. Show what is left`}
                  className="inline-flex min-h-8 items-center gap-0.5 whitespace-nowrap rounded px-1 text-xs font-medium text-warning underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <span className="hidden xl:inline">{shownText}</span>
                  <span className="xl:hidden">{`${shownText.split(' ')[0]} to finish`}</span>
                  <ChevronDown className="h-3.5 w-3.5" aria-hidden />
                </button>
              </PopoverTrigger>
            </>
          )}
        </span>
      </PopoverAnchor>
      <PopoverContent align="end" className="w-[380px] max-w-[calc(100vw-1.5rem)] p-0" data-testid="flow-issues-popover">
        <div className="border-b border-border px-3.5 py-3">
          <p className="text-sm font-semibold" data-testid="flow-issues-title">{text}</p>
          <p className="mt-0.5 text-xs text-muted-foreground" data-testid="flow-issues-note">
            {live
              ? 'This flow is live, so it has to be finished before it can be saved. Finish these, or unpublish it to keep working on a draft.'
              : 'Your changes are saved. A flow needs these done before it can run or be published.'}
          </p>
        </div>
        <ul className="max-h-[min(60vh,420px)] divide-y divide-border overflow-y-auto" data-testid="flow-issues-list">
          {groups.map((g) => (
            <li key={g.nodeId || 'flow'} className="px-3.5 py-2.5" data-testid={`flow-issues-step-${g.nodeId || 'flow'}`}>
              <p className="truncate text-xs font-semibold" title={g.nodeId ? g.label : 'The flow'}>{g.nodeId ? g.label : 'The flow'}</p>
              <ul className="mt-1 space-y-1.5">
                {g.issues.map((i) => (
                  <li key={`${i.field}-${i.message}`} className="flex items-start gap-2" data-testid={`flow-issues-row-${g.nodeId || 'flow'}-${i.field}`}>
                    <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" aria-hidden />
                    <span className="min-w-0 flex-1 text-xs leading-snug">{i.message}</span>
                    {g.nodeId && (
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="shrink-0"
                        data-testid={`flow-issues-fix-${g.nodeId}-${i.field}`}
                        onClick={() => {
                          setChecklistOpen(false);
                          setSelectedNode(g.nodeId);
                          requestFocus(g.nodeId, i.field);
                        }}
                      >
                        Fix
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      </PopoverContent>
    </Popover>
  );
}
