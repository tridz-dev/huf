import { useMemo } from 'react';
import { ChevronRight } from 'lucide-react';
import { useFlowContext } from '@/contexts/FlowContext';
import { cardIcon } from '@/components/nodes/nodeIcons';
import { actionSubtitle, cardStatus, triggerSubtitle, type CardStatusKind } from '@/lib/flow/flowNodeCard';
import { orderSteps } from './stepsOrder';
import { validateNode } from '@/lib/flow-graph/flowValidation';
import { cn } from '@/lib/utils';

const STATUS_TONE: Record<CardStatusKind, string> = {
  ready: 'text-steel',
  'needs-setup': 'text-warning',
  'not-connected': 'text-warning',
  orphan: 'text-warning',
  running: 'text-info',
  waiting: 'text-warning',
  done: 'text-good',
  failed: 'text-destructive',
  skipped: 'text-steel',
  stopped: 'text-steel',
};

/**
 * A phone's default view of a flow: its steps from the trigger down as plain cards (icon, title, one line of what it does,
 * how it is doing). Reading and checking, not editing; tap a step to read its settings. The map is behind "Show map".
 */
export function FlowStepsList() {
  const { activeFlow, setSelectedNode } = useFlowContext();
  const steps = useMemo(() => (activeFlow ? orderSteps(activeFlow.nodes, activeFlow.edges) : []), [activeFlow]);
  if (!activeFlow) return null;
  const byId = new Map(activeFlow.nodes.map((n) => [n.id, n]));
  return (
    <div className="h-full overflow-y-auto bg-background px-4 pb-4 pt-3" data-testid="flow-steps-list">
      <h2 className="sr-only">Steps</h2>
      <ol className="space-y-2">
        {steps.map((step) => {
          const node = byId.get(step.id);
          if (!node) return null;
          const data = node.data;
          const Icon = cardIcon(data);
          const unsetTrigger = data.nodeType === 'trigger' && !data.triggerConfig?.type;
          const title = unsetTrigger ? 'No trigger yet' : data.label || 'Step';
          const summary =
            data.nodeType === 'trigger' ? triggerSubtitle(data.triggerConfig)
              : data.nodeType === 'end' ? 'The flow finishes here'
                : actionSubtitle(data.actionConfig);
          const status = cardStatus({
            runStatus: data.status,
            incomplete: validateNode({ id: node.id, data }, activeFlow.edges).length > 0,
            orphaned: false,
            notConnected: false,
          });
          return (
            <li key={step.id} className={cn(step.depth > 0 && 'ml-4 border-l-2 border-line pl-3')}>
              {step.branch && <p className="mb-1 text-xs font-medium text-steel" data-testid={`flow-step-branch-${step.id}`}>{step.branch}</p>}
              <button
                type="button"
                data-testid={`flow-step-card-${step.id}`}
                onClick={() => setSelectedNode(step.id)}
                className="flex min-h-[56px] w-full items-center gap-3 rounded-lg border border-line bg-panel px-3 py-2 text-left active:bg-paper-deep"
              >
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-paper-deep text-ink">
                  <Icon className="h-4 w-4" aria-hidden />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium text-ink" data-testid={`flow-step-card-title-${step.id}`}>{title}</span>
                  <span className="block truncate text-xs text-steel" data-testid={`flow-step-card-summary-${step.id}`}>{summary}</span>
                </span>
                <span className={cn('shrink-0 text-xs font-medium', STATUS_TONE[status.kind])} data-testid={`flow-step-card-status-${step.id}`}>{status.text}</span>
                <ChevronRight className="h-4 w-4 shrink-0 text-steel-soft" aria-hidden />
              </button>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
