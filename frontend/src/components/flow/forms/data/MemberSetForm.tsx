import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { useFlowContext } from '@/contexts/FlowContext';
import { isGatewayKindId } from '@/lib/flow-gateway/gatewayWords';
import { Label } from '../../../ui/label';
import { FieldHint } from '../../FieldHint';
import { KeyValueRows } from '../fields';
import { type ActionFormProps, Section } from '../formKit';

/** Chat messages and document events say who a run is about; a web request or a timer does not. */
export function triggerNamesAPerson(triggerType: unknown): boolean {
  return triggerType === 'doc-event' || isGatewayKindId(triggerType);
}

/** Remember for this person: values kept for the person the run is about, across runs of this flow. */
export function MemberSetForm({ nodeId, cfg, patch, f, Err, title }: ActionFormProps) {
  const { canManage } = useFlowPermissions();
  const { activeFlow } = useFlowContext();
  const trigger = activeFlow?.nodes.find((n) => n.data.nodeType === 'trigger')?.data.triggerConfig as { type?: string } | undefined;
  const knowsPerson = !trigger?.type || triggerNamesAPerson(trigger.type);
  return (
    <Section title={title} hint="Kept for this person across runs of this flow, until removed.">
      {!knowsPerson && (
        <p className="rounded-md bg-muted/30 p-2 text-xs text-muted-foreground" data-testid="flow-member-set-disabled">
          This flow's trigger does not say who the run is about, so there is no one to remember values for.
        </p>
      )}
      <div>
        <Label size="sm">Values to remember</Label>
        <KeyValueRows testId={f('vars')} nodeId={nodeId} disabled={!canManage} keyLabel="Name" addLabel="Add a value to remember" value={cfg.vars} onChange={(vars) => patch({ vars: vars ?? {} })} />
        <FieldHint testId="flow-hint-member-set-vars">Kept for this person across runs of this flow, until removed.</FieldHint>
        <Err field="vars" />
      </div>
    </Section>
  );
}
