import { useEffect } from 'react';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { useStepGateways } from '@/hooks/flow/useStepGateways';
import { useFlowContext } from '@/contexts/FlowContext';
import { Combobox } from '../../../ui/combobox';
import { Label } from '../../../ui/label';
import { FieldHint } from '../../FieldHint';
import { type ActionFormProps, str } from '../formKit';

/** What an app-owned flow's handoff may not choose: it hands over the run's own member and sends nothing. */
export const HANDOFF_FIXED_FIELDS = ['conversation', 'gateway', 'recipient', 'message'];

/**
 * The fixed part of a handoff step in the embedded editor of an app-owned flow: the channel, picked from the ones the
 * flow's app lists, and the member-only settings the server's save and publish checks require.
 */
export function AppHandoffFields({ cfg, patch, f, Err }: Pick<ActionFormProps, 'cfg' | 'patch' | 'f' | 'Err'>) {
  const { canManage } = useFlowPermissions();
  const { activeFlow } = useFlowContext();
  const { gateways, failed } = useStepGateways(activeFlow?.id, canManage);
  const gateway = str(cfg.gateway);
  const options = (gateways ?? []).map((g) => ({ value: g.name, label: g.label || g.name }));
  const memberOnly = cfg.recipient === '$member' && cfg.message === '' && cfg.conversation === undefined;

  useEffect(() => {
    if (canManage && !memberOnly) patch({ recipient: '$member', message: '', conversation: undefined });
  }, [canManage, memberOnly, patch]);

  return (
    <div>
      <Label htmlFor="handoff-gateway" size="sm">Channel</Label>
      <Combobox
        id="handoff-gateway"
        testId={f('gateway')}
        options={gateway && !options.some((o) => o.value === gateway) ? [{ value: gateway, label: gateway }, ...options] : options}
        value={gateway}
        disabled={!canManage || (!gateways && !failed)}
        onValueChange={(v) => v && patch({ gateway: v })}
        placeholder={gateways || failed ? 'Choose a channel...' : 'Loading...'}
        searchPlaceholder="Search channels..."
        emptyText={failed ? 'Could not load your channels. Try again.' : 'No channel is available yet.'}
      />
      <FieldHint testId="flow-hint-handoff-member">Hands over the conversation of the person this run is about. No message is sent to them.</FieldHint>
      <Err field="gateway" />
    </div>
  );
}
