import { Plus, Trash2 } from 'lucide-react';
import { Button } from '../../../ui/button';
import { Input } from '../../../ui/input';
import { Label } from '../../../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../ui/select';
import { FieldHint } from '../../FieldHint';
import { type ActionFormProps, Section } from '../formKit';
import { useFlowContext } from '../../../../contexts/FlowContext';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { buildBranchOptionLabels, findUpstreamNodeIds } from '@/lib/flow/flowBranchTargets';
import { SPLIT_LABEL_MAX, SPLIT_SALT_MAX, splitProblems, splitWeightTotal } from '@/lib/flow-steps/splitConfig';
import { edgeRoute, makeFlowEdge, makeFlowEdgeId } from '../../../../services/flowSerializer';
import type { FlowEdge } from '../../../../types/flow.types';

function freeOptionIndex(edges: FlowEdge[], source: string, target: string): number {
  let i = 0;
  while (edges.some((e) => e.id === makeFlowEdgeId(source, 'option', target, i))) i++;
  return i;
}

/** Parses a share typed into a number box; empty stays undefined so the check can ask for it. */
const toNumber = (raw: string): number | undefined => (raw.trim() === '' ? undefined : Number(raw));

/**
 * The Split audience step (graph-IR `split`): weighted branches (the step's option edges, each with a `weight`
 * in percent), a holdout share and an optional bucketing salt. Held-out people still walk the graph; only
 * marketing sends are skipped for them.
 */
export function SplitForm({ nodeId, cfg, patch, f, Err, title }: ActionFormProps) {
  const { activeFlow, updateEdges } = useFlowContext();
  const { canManage } = useFlowPermissions();
  const edges = activeFlow?.edges ?? [];
  const nodes = activeFlow?.nodes ?? [];

  const branches = edges.filter((e) => e.source === nodeId && edgeRoute(e) === 'option');
  const candidates = nodes.filter((n) => n.id !== nodeId);
  const upstream = findUpstreamNodeIds(edges, nodeId);
  const targetLabels = buildBranchOptionLabels(candidates.map((n) => ({ id: n.id, data: { label: n.data.label } })), upstream);
  const nameOf = (id: string) => nodes.find((n) => n.id === id)?.data.label || id;
  const firstTarget = candidates.find((n) => !upstream.has(n.id)) ?? candidates[0];

  const arms = branches.map((e) => ({ label: e.label, weight: e.data?.weight }));
  const total = splitWeightTotal(arms);
  const problems = splitProblems(arms, cfg.holdout, cfg.salt);
  const problem = (field: string) => problems.find((p) => p.field === field)?.message;

  const replace = (id: string, change: (e: FlowEdge) => FlowEdge) => updateEdges(edges.map((e) => (e.id === id ? change(e) : e)));

  const addBranch = () => {
    if (!firstTarget) return;
    const index = freeOptionIndex(edges, nodeId, firstTarget.id);
    const remaining = Math.max(0, 100 - total);
    const label = `Branch ${String.fromCharCode(65 + (branches.length % 26))}`;
    updateEdges([...edges, makeFlowEdge(nodeId, firstTarget.id, 'option', { label, index, weight: remaining })]);
  };

  const holdout = typeof cfg.holdout === 'number' ? cfg.holdout : cfg.holdout === undefined ? '' : String(cfg.holdout);
  const salt = typeof cfg.salt === 'string' ? cfg.salt : '';

  return (
    <Section title={title} hint="Each person gets one branch by share. The same person always lands in the same branch.">
      <div className="space-y-2" data-testid="flow-split-branches">
        <Label size="sm">Branches</Label>
        {branches.length === 0 ? <p className="text-xs text-muted-foreground" data-testid="flow-split-empty">Add at least two branches.</p> : null}
        {branches.map((b, i) => (
          <div key={b.id} className="space-y-2 rounded-md border border-border p-2" data-testid={`flow-split-branch-${i}`}>
            <div className="flex items-center gap-1">
              <Input
                className="min-w-0 flex-1"
                maxLength={SPLIT_LABEL_MAX}
                aria-label={`Name of branch ${i + 1}`}
                data-testid={`flow-split-name-${i}`}
                value={typeof b.label === 'string' ? b.label : ''}
                placeholder="Name this branch, for example Offer A"
                disabled={!canManage}
                onChange={(ev) => replace(b.id, (e) => ({ ...e, label: ev.target.value }))}
              />
              <Input
                className="w-20"
                type="number"
                min={0}
                max={100}
                step={1}
                aria-label={`Share of branch ${i + 1} in percent`}
                data-testid={`flow-split-weight-${i}`}
                value={typeof b.data?.weight === 'number' ? b.data.weight : ''}
                disabled={!canManage}
                onChange={(ev) => replace(b.id, (e) => ({ ...e, data: { ...e.data, weight: toNumber(ev.target.value) } }))}
              />
              <span className="text-xs text-muted-foreground">%</span>
              <Button type="button" variant="ghost" size="icon" aria-label="Remove branch" disabled={!canManage} onClick={() => updateEdges(edges.filter((e) => e.id !== b.id))} data-testid={`flow-split-remove-${i}`}>
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </div>
            <div>
              <Label size="sm" htmlFor={`flow-split-target-${b.id}`}>Then go to</Label>
              <Select
                value={b.target}
                disabled={!canManage}
                onValueChange={(target) => replace(b.id, (e) => ({ ...e, id: makeFlowEdgeId(nodeId, 'option', target, freeOptionIndex(edges, nodeId, target)), target }))}
              >
                <SelectTrigger id={`flow-split-target-${b.id}`} data-testid={`flow-split-target-${i}`}>
                  <SelectValue placeholder="Choose where this branch goes..." />
                </SelectTrigger>
                <SelectContent>
                  {candidates.map((n) => (
                    <SelectItem key={n.id} value={n.id}>{targetLabels.get(n.id) ?? nameOf(n.id)}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        ))}
        <Button type="button" variant="outline" size="sm" onClick={addBranch} disabled={!canManage || !firstTarget} data-testid="flow-split-add">
          <Plus className="mr-1 h-3.5 w-3.5" />
          Add branch
        </Button>
        <p className={`text-xs ${total === 100 ? 'text-muted-foreground' : 'text-destructive'}`} data-testid="flow-split-total">
          Total {total}% of 100%
        </p>
        {problem('options') ? <p className="text-xs text-destructive" role="alert" data-testid="flow-split-problem">{problem('options')}</p> : null}
        <Err field="options" />
      </div>
      <div className="space-y-1">
        <Label htmlFor="flow-split-holdout" size="sm">Hold out (percent)</Label>
        <Input
          id="flow-split-holdout"
          type="number"
          min={0}
          max={100}
          step={1}
          data-testid={f('holdout')}
          value={holdout}
          disabled={!canManage}
          onChange={(e) => patch({ holdout: toNumber(e.target.value) })}
        />
        <FieldHint testId="flow-hint-split-holdout">Held-out people still go through the flow but get no marketing messages.</FieldHint>
        {problem('holdout') ? <p className="text-xs text-destructive" role="alert" data-testid="flow-split-holdout-problem">{problem('holdout')}</p> : null}
        <Err field="holdout" />
      </div>
      <div className="space-y-1">
        <Label htmlFor="flow-split-salt" size="sm">Salt (optional)</Label>
        <Input
          id="flow-split-salt"
          data-testid={f('salt')}
          maxLength={SPLIT_SALT_MAX}
          value={salt}
          placeholder="Defaults to the flow version"
          disabled={!canManage}
          onChange={(e) => patch({ salt: e.target.value.trim() ? e.target.value : undefined })}
        />
        <FieldHint testId="flow-hint-split-salt">Change it to reshuffle who lands in which branch.</FieldHint>
        <Err field="salt" />
      </div>
    </Section>
  );
}
