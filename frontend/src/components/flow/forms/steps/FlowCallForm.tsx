import { useEffect, useMemo, useState } from 'react';
import { useFlowContext } from '../../../../contexts/FlowContext';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { getFlowDefinitions, type FlowDefinitionListItem } from '@/services/flowApi';
import { Combobox } from '../../../ui/combobox';
import { Label } from '../../../ui/label';
import { Switch } from '../../../ui/switch';
import { FieldHint } from '../../FieldHint';
import { KeyValueRows } from '../fields';
import { type ActionFormProps, Section } from '../formKit';

/** Run another flow: pick a published flow, give it values, and optionally wait for it to finish. */
export function FlowCallForm({ nodeId, cfg, patch, f, Err, title }: ActionFormProps) {
  const { activeFlow } = useFlowContext();
  const { canManage } = useFlowPermissions();
  const [flows, setFlows] = useState<FlowDefinitionListItem[] | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let live = true;
    getFlowDefinitions({ status: 'Active' }).then((l) => live && setFlows(l)).catch(() => { if (live) { setFlows([]); setFailed(true); } });
    return () => { live = false; };
  }, []);
  const options = useMemo(
    () => (flows ?? []).filter((x) => x.flow_id !== activeFlow?.id).map((x) => ({ value: x.flow_id, label: x.flow_name })),
    [flows, activeFlow?.id],
  );
  const flowId = typeof cfg.flow_id === 'string' ? cfg.flow_id : '';
  const waits = cfg.mode === 'wait';
  return (
    <Section title={title} hint="Starts a published flow. It can send values to it and wait for it to finish.">
      <div>
        <Label htmlFor="flow-call-flow" size="sm">Flow</Label>
        <Combobox
          id="flow-call-flow"
          testId={f('flow_id')}
          options={flowId && !options.some((o) => o.value === flowId) ? [{ value: flowId, label: flowId }, ...options] : options}
          value={flowId}
          disabled={!canManage || flows === null}
          onValueChange={(v) => v && patch({ flow_id: v })}
          placeholder={flows === null ? 'Loading...' : 'Choose a flow...'}
          searchPlaceholder="Search flows..."
          emptyText={failed ? 'Could not load flows. Try again.' : 'There are no other published flows yet.'}
        />
        <Err field="flow_id" />
      </div>
      <div>
        <Label size="sm">Send it</Label>
        <KeyValueRows testId={f('input')} nodeId={nodeId} disabled={!canManage} addLabel="Add a value" value={cfg.input} onChange={(input) => patch({ input: input ?? {} })} />
      </div>
      <div className="flex items-center gap-2">
        <Switch id="flow-call-wait" data-testid={f('mode')} disabled={!canManage} checked={waits} onCheckedChange={(on) => patch({ mode: on ? 'wait' : 'fire_and_forget' })} />
        <Label htmlFor="flow-call-wait" size="sm">Wait for it to finish</Label>
      </div>
      {waits && <FieldHint testId="flow-hint-flow-call-wait">This flow pauses until the other one finishes. Its result is available to later steps.</FieldHint>}
    </Section>
  );
}
