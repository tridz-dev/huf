import { ArrowRight, Plus, Trash2 } from 'lucide-react';
import { Input } from '../../ui/input';
import { Label } from '../../ui/label';
import { Button } from '../../ui/button';
import { cn } from '@/lib/utils';
import { useFlowContext } from '../../../contexts/FlowContext';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { edgeRoute } from '../../../services/flowSerializer';
import { edgeRule } from '@/lib/flow-graph/edgeRule';
import { requestEdgeAction } from '@/lib/flow-graph/edgeActions';
import type { FlowNode } from '../../../types/flow.types';

function StepChip({ node, testId, onSelect }: { node: FlowNode | undefined; testId: string; onSelect: (id: string) => void }) {
  const title = node?.data.label || 'Step';
  const kind = node?.data.nodeType === 'trigger' ? 'Trigger' : node?.data.nodeType === 'end' ? 'End' : 'Step';
  return (
    <button
      type="button"
      data-testid={testId}
      title={`Show "${title}"`}
      disabled={!node}
      onClick={() => node && onSelect(node.id)}
      className="flex min-w-0 flex-1 flex-col items-start rounded-md border border-line bg-panel px-2 py-1.5 text-left hover:border-steel-soft"
    >
      <span className="text-xs text-muted-foreground">{kind}</span>
      <span className="w-full truncate text-sm font-medium">{title}</span>
    </button>
  );
}

/** Side panel for a selected connection: which step leads to which, the rule in one plain sentence, and what you can do. */
export function EdgeConnectionPanel({ edgeId }: { edgeId: string }) {
  const { activeFlow, updateEdges, setSelectedNode } = useFlowContext();
  const { canManage } = useFlowPermissions();
  const edge = activeFlow?.edges.find((e) => e.id === edgeId);
  if (!activeFlow || !edge) return null;
  const route = edgeRoute(edge);
  const from = activeFlow.nodes.find((n) => n.id === edge.source);
  const to = activeFlow.nodes.find((n) => n.id === edge.target);
  const rule = edgeRule(route, from?.data.label || 'this step', to?.data.label || 'the next step', from?.data.actionConfig as { type?: string } | undefined, typeof edge.label === 'string' ? edge.label : undefined);
  return (
    <div className="space-y-3" data-testid="flow-edge-config">
      <div className="flex items-center gap-2">
        <div className="text-sm font-semibold">Connection</div>
        <span
          data-testid="flow-edge-kind"
          className={cn('rounded-full border px-2 py-0.5 text-xs font-medium', rule.loop ? 'border-line-dark bg-paper-deep text-ink-soft' : 'border-line bg-panel text-muted-foreground')}
        >
          {rule.heading}
        </span>
      </div>
      <div className="flex items-stretch gap-1.5" data-testid="flow-edge-ends">
        <StepChip node={from} testId="flow-edge-from" onSelect={setSelectedNode} />
        <ArrowRight className="mt-5 h-4 w-4 shrink-0 text-muted-foreground" aria-label="leads to" />
        <StepChip node={to} testId="flow-edge-to" onSelect={setSelectedNode} />
      </div>
      <p className="text-xs text-muted-foreground" data-testid="flow-edge-meaning">{rule.sentence}</p>
      {route === 'option' ? (
        <div>
          <Label htmlFor="edge-label" size="sm">Path name</Label>
          <Input
            id="edge-label"
            data-testid="flow-edge-label"
            value={(edge.label as string) || ''}
            onChange={(e) => updateEdges(activeFlow.edges.map((x) => (x.id === edge.id ? { ...x, label: e.target.value } : x)))}
            placeholder="For example: urgent"
          />
          <p className="mt-1 text-xs text-muted-foreground">The AI picks the path whose name fits best.</p>
        </div>
      ) : null}
      {canManage && (
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" size="sm" data-testid="flow-edge-panel-insert" onClick={() => requestEdgeAction({ type: 'insert', edgeId })}>
            <Plus className="mr-1.5 h-4 w-4" />
            Add a step here
          </Button>
          <Button type="button" variant="outline" size="sm" className="text-destructive hover:bg-destructive/10" data-testid="flow-edge-panel-remove" onClick={() => requestEdgeAction({ type: 'remove', edgeId })}>
            <Trash2 className="mr-1.5 h-4 w-4" />
            Remove connection
          </Button>
        </div>
      )}
    </div>
  );
}
