import { Plus } from 'lucide-react';
import { Button } from '../../ui/button';
import { useFlowContext } from '@/contexts/FlowContext';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { branchHandlesFor, branchTone, type BranchTone } from '@/lib/flow/flowBranches';
import { requestAddStep } from '@/lib/flow-graph/edgeActions';
import { edgeRoute } from '../../../services/flowSerializer';
import { cn } from '@/lib/utils';

const TONE: Record<BranchTone, string> = {
  good: 'border-good/40 bg-good-tint text-good',
  bad: 'border-destructive/40 bg-destructive-tint text-destructive',
  warn: 'border-signal/50 bg-panel text-signal-ink',
  loop: 'border-line-dark bg-paper-deep text-ink-soft',
  neutral: 'border-line-dark bg-panel text-ink-soft',
};

/** Where the Yes path and the No path go: "Yes -> Big order", with an Add step button for each. */
export function ConditionBranches({ nodeId, cfg }: { nodeId: string; cfg: Record<string, unknown> }) {
  const { activeFlow, setSelectedNode } = useFlowContext();
  const { canManage } = useFlowPermissions();
  const handles = branchHandlesFor('condition', cfg);
  return (
    <div className="space-y-1.5" data-testid="flow-branches">
      <p className="text-xs font-medium">Where each path goes</p>
      {handles.map((h) => {
        const edge = activeFlow?.edges.find((e) => e.source === nodeId && edgeRoute(e) === h.route);
        const target = activeFlow?.nodes.find((n) => n.id === edge?.target);
        return (
          <div key={h.route} className="flex items-center gap-2 rounded-md border border-border px-2 py-1.5 text-xs" data-testid={`flow-branch-${h.route}`}>
            <span className={cn('shrink-0 rounded-full border px-2 py-0.5 font-medium', TONE[branchTone(h.route)])}>{h.label}</span>
            <span aria-hidden className="text-muted-foreground">→</span>
            {target ? (
              <button type="button" className="min-w-0 flex-1 truncate text-left text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal" onClick={() => setSelectedNode(target.id)} data-testid={`flow-branch-${h.route}-target`}>
                {target.data.label}
              </button>
            ) : (
              <span className="min-w-0 flex-1 truncate text-muted-foreground" data-testid={`flow-branch-${h.route}-empty`}>Not connected</span>
            )}
            {canManage && (
              <Button type="button" variant="ghost" size="sm" className="shrink-0" data-testid={`flow-branch-${h.route}-add`} aria-label={`Add step to the ${h.label} path`} onClick={() => requestAddStep({ sourceNodeId: nodeId, route: h.route })}>
                <Plus className="mr-1 h-3.5 w-3.5" />
                Add step
              </Button>
            )}
          </div>
        );
      })}
    </div>
  );
}
