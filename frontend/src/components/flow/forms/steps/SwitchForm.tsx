import { ArrowDown, ArrowUp, Plus, Trash2 } from 'lucide-react';
import { Button } from '../../../ui/button';
import { Input } from '../../../ui/input';
import { Label } from '../../../ui/label';
import { Checkbox } from '../../../ui/checkbox';
import { Textarea } from '../../../ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../ui/select';
import { FieldHint } from '../../FieldHint';
import { ConditionBuilder } from '../../condition/ConditionBuilder';
import { RawExpression } from '../../condition/RawExpression';
import { type ActionFormProps, Section } from '../formKit';
import { useFlowContext } from '../../../../contexts/FlowContext';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { parseCondition } from '@/lib/flow-condition/parse';
import { buildBranchOptionLabels, findUpstreamNodeIds } from '@/lib/flow/flowBranchTargets';
import { edgeRoute, makeFlowEdge, makeFlowEdgeId } from '../../../../services/flowSerializer';
import { AI_CHOICE_TITLE } from '../../../../services/flow/serializerTables';
import type { FlowEdge } from '../../../../types/flow.types';

/** Longest rule name shown as the branch label on the canvas. */
export const RULE_NAME_MAX = 60;

/** Smallest index whose option edge id from `source` to `target` is not taken yet. */
function freeOptionIndex(edges: FlowEdge[], source: string, target: string): number {
  let i = 0;
  while (edges.some((e) => e.id === makeFlowEdgeId(source, 'option', target, i))) i++;
  return i;
}

/**
 * The Choose by rules step (router.decision): rules checked from the top, the first one whose check holds
 * takes its path, otherwise the "Otherwise go to" path. Rules and paths are the step's option and default edges.
 */
export function SwitchForm({ nodeId, cfg, patch, Err, title }: ActionFormProps) {
  const { activeFlow, updateEdges, updateNodeData } = useFlowContext();
  const { canManage } = useFlowPermissions();
  const edges = activeFlow?.edges ?? [];
  const nodes = activeFlow?.nodes ?? [];

  const decision = cfg.decision !== null && typeof cfg.decision === 'object' ? (cfg.decision as Record<string, unknown>) : null;
  const setDecision = (change: Record<string, unknown>) => {
    const next: Record<string, unknown> = { ...decision, ...change };
    for (const k of Object.keys(change)) if (change[k] === undefined) delete next[k];
    patch({ decision: next });
  };
  // A step still named after its mode follows the mode; a name the user chose is kept.
  const setAiMode = (on: boolean) => {
    patch({ decision: on ? { ...(decision ?? {}) } : undefined });
    const [from, to] = on ? [title, AI_CHOICE_TITLE] : [AI_CHOICE_TITLE, title];
    updateNodeData(nodeId, (data) => (!data.label || data.label === from ? { ...data, label: to } : data));
  };
  const confidence = typeof decision?.minimum_confidence === 'number' ? decision.minimum_confidence : undefined;

  const rules = edges.filter((e) => e.source === nodeId && edgeRoute(e) === 'option');
  const otherwise = edges.find((e) => e.source === nodeId && edgeRoute(e) === 'default')?.target ?? '';

  const candidates = nodes.filter((n) => n.id !== nodeId);
  const upstream = findUpstreamNodeIds(edges, nodeId);
  const targetLabels = buildBranchOptionLabels(
    candidates.map((n) => ({ id: n.id, data: { label: n.data.label } })),
    upstream,
  );
  const nameOf = (id: string) => nodes.find((n) => n.id === id)?.data.label || id;
  const firstTarget = candidates.find((n) => !upstream.has(n.id)) ?? candidates[0];

  const replaceRule = (id: string, change: (e: FlowEdge) => FlowEdge) =>
    updateEdges(edges.map((e) => (e.id === id ? change(e) : e)));

  const addRule = () => {
    if (!firstTarget) return;
    const index = freeOptionIndex(edges, nodeId, firstTarget.id);
    const rule = makeFlowEdge(nodeId, firstTarget.id, 'option', { label: nameOf(firstTarget.id), index, expression: '' });
    updateEdges([...edges, rule]);
  };

  const moveRule = (id: string, by: -1 | 1) => {
    const at = edges.findIndex((e) => e.id === id);
    const isRule = (e: FlowEdge) => e.source === nodeId && edgeRoute(e) === 'option';
    let near = -1;
    if (by < 0) {
      for (let i = at - 1; i >= 0 && near < 0; i--) if (isRule(edges[i])) near = i;
    } else {
      for (let i = at + 1; i < edges.length && near < 0; i++) if (isRule(edges[i])) near = i;
    }
    if (near < 0) return;
    const next = [...edges];
    [next[at], next[near]] = [next[near], next[at]];
    updateEdges(next);
  };

  const removeRule = (id: string) => updateEdges(edges.filter((e) => e.id !== id));

  const setOtherwise = (target: string) => {
    const kept = edges.filter((e) => !(e.source === nodeId && edgeRoute(e) === 'default'));
    // The canvas draws every path of a rule step from its one option handle.
    updateEdges([...kept, { ...makeFlowEdge(nodeId, target, 'default'), sourceHandle: 'option' }]);
  };

  return (
    <Section title={decision ? AI_CHOICE_TITLE : title} hint={decision ? 'The AI picks one of the paths below. When it is unsure, the flow takes the unsure path.' : 'Checks each rule from the top. The first one that matches takes its path.'}>
      <div className="space-y-2 rounded-md border border-border p-2" data-testid="flow-switch-decision">
        <div className="flex items-center gap-2">
          <Checkbox id="flow-switch-ai" data-testid="flow-switch-ai" disabled={!canManage} checked={decision !== null}
            onCheckedChange={(on) => setAiMode(on === true)} />
          <Label htmlFor="flow-switch-ai" size="sm">Let AI choose the path</Label>
        </div>
        {decision ? (
          <>
            <div>
              <Label htmlFor="flow-switch-instructions" size="sm">How to choose</Label>
              <Textarea id="flow-switch-instructions" data-testid="flow-switch-instructions" disabled={!canManage} rows={3}
                placeholder="For example: pick the team that should answer this message."
                value={typeof decision.instructions === 'string' ? decision.instructions : ''}
                onChange={(e) => setDecision({ instructions: e.target.value === '' ? undefined : e.target.value })} />
              <Err field="decision" />
            </div>
            <div>
              <Label htmlFor="flow-switch-confidence" size="sm">Lowest confidence to accept (0 to 1)</Label>
              <Input id="flow-switch-confidence" data-testid="flow-switch-confidence" type="number" min={0} max={1} step={0.05} disabled={!canManage}
                value={confidence === undefined ? '' : String(confidence)}
                onChange={(e) => {
                  const v = e.target.value.trim() === '' ? undefined : Math.min(1, Math.max(0, Number(e.target.value)));
                  setDecision({ minimum_confidence: v });
                }} />
              <FieldHint>Below this, the flow takes the unsure path. Leave empty to accept any answer.</FieldHint>
            </div>
          </>
        ) : null}
      </div>
      <div className="space-y-2" data-testid="flow-switch-rules">
        <Label size="sm">Rules</Label>
        {rules.length === 0 ? (
          <p className="text-xs text-muted-foreground" data-testid="flow-switch-empty">Add a rule to choose between paths.</p>
        ) : null}
        {rules.map((rule, i) => {
          const expression = typeof rule.data?.expression === 'string' ? rule.data.expression : '';
          const handWritten = parseCondition(expression) === null;
          return (
            <div key={rule.id} className="space-y-2 rounded-md border border-border p-2" data-testid={`flow-switch-rule-${rule.target}`}>
              <div className="flex items-center gap-1">
                <Input
                  className="min-w-0 flex-1"
                  maxLength={RULE_NAME_MAX}
                  aria-label={`Name of rule ${i + 1}`}
                  data-testid={`flow-switch-rule-name-${rule.target}`}
                  value={typeof rule.label === 'string' ? rule.label : ''}
                  placeholder="Name this rule, for example Urgent"
                  disabled={!canManage}
                  onChange={(ev) => replaceRule(rule.id, (e) => ({ ...e, label: ev.target.value }))}
                />
                <Button type="button" variant="ghost" size="icon" aria-label="Move rule up" disabled={!canManage || i === 0} onClick={() => moveRule(rule.id, -1)} data-testid={`flow-switch-up-${rule.target}`}>
                  <ArrowUp className="h-3.5 w-3.5" />
                </Button>
                <Button type="button" variant="ghost" size="icon" aria-label="Move rule down" disabled={!canManage || i === rules.length - 1} onClick={() => moveRule(rule.id, 1)} data-testid={`flow-switch-down-${rule.target}`}>
                  <ArrowDown className="h-3.5 w-3.5" />
                </Button>
                <Button type="button" variant="ghost" size="icon" aria-label="Remove rule" disabled={!canManage} onClick={() => removeRule(rule.id)} data-testid={`flow-switch-remove-${rule.target}`}>
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
              {handWritten && expression !== '' ? (
                <RawExpression
                  nodeId={nodeId}
                  value={expression}
                  onChange={(v) => replaceRule(rule.id, (e) => ({ ...e, data: { ...e.data, expression: v } }))}
                  testId={`flow-switch-expression-${rule.target}`}
                  canEdit={canManage}
                  handWritten
                />
              ) : (
                <ConditionBuilder
                  nodeId={nodeId}
                  expression={expression}
                  disabled={!canManage}
                  onChange={(v) => replaceRule(rule.id, (e) => ({ ...e, data: { ...e.data, expression: v } }))}
                />
              )}
              <div>
                <Label size="sm" htmlFor={`flow-switch-target-${rule.id}`}>Then go to</Label>
                <Select
                  value={rule.target}
                  disabled={!canManage}
                  onValueChange={(target) =>
                    replaceRule(rule.id, (e) => ({ ...e, id: makeFlowEdgeId(nodeId, 'option', target, freeOptionIndex(edges, nodeId, target)), target }))
                  }
                >
                  <SelectTrigger id={`flow-switch-target-${rule.id}`} data-testid={`flow-switch-target-select-${rule.target}`}>
                    <SelectValue placeholder="Choose where this rule goes..." />
                  </SelectTrigger>
                  <SelectContent>
                    {candidates.map((n) => (
                      <SelectItem key={n.id} value={n.id}>{targetLabels.get(n.id) ?? nameOf(n.id)}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          );
        })}
        <Button type="button" variant="outline" size="sm" onClick={addRule} disabled={!canManage || !firstTarget} data-testid="flow-switch-add-rule">
          <Plus className="mr-1 h-3.5 w-3.5" />
          Add rule
        </Button>
        {!firstTarget ? <FieldHint testId="flow-switch-no-steps">Add another step first, then the rule can go there.</FieldHint> : null}
        <FieldHint testId="flow-switch-hint">Rules are checked from the top. The first one that matches is used.</FieldHint>
        <Err field="options" />
      </div>
      <div className="space-y-1">
        <Label htmlFor="flow-switch-otherwise" size="sm">{decision ? 'When unsure, go to' : 'Otherwise go to'}</Label>
        <Select value={otherwise || undefined} onValueChange={setOtherwise} disabled={!canManage}>
          <SelectTrigger id="flow-switch-otherwise" data-testid="flow-switch-otherwise">
            <SelectValue placeholder={decision ? 'Choose where to go when the AI is unsure.' : 'Choose where to go when no rule matches.'} />
          </SelectTrigger>
          <SelectContent>
            {candidates.map((n) => (
              <SelectItem key={n.id} value={n.id}>{targetLabels.get(n.id) ?? nameOf(n.id)}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Err field="default" />
      </div>
    </Section>
  );
}
