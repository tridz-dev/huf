import { useState } from 'react';
import { Button } from '../../ui/button';
import { NodeSelectionModal } from '../../modals/NodeSelectionModal';
import { DataTriggerForm } from './DataTriggerForm';
import { ScheduleTriggerForm } from './ScheduleTriggerForm';
import { WebhookTriggerForm } from './WebhookTriggerForm';
import { Section } from './formKit';
import { triggerLabel } from '@/lib/flow/flowLabels';
import { triggerOptions } from '@/data/triggers';
import { useFlowContext } from '@/contexts/FlowContext';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { type TriggerConfig } from '@/types/flow.types';

/** The settings of the step that starts the flow: one panel per trigger kind, or the way to choose one. */
export function TriggerConfigForm({ nodeId }: { nodeId: string }) {
  const { activeFlow, updateNode } = useFlowContext();
  const { canManage } = useFlowPermissions();
  const [choosing, setChoosing] = useState(false);
  const node = activeFlow?.nodes.find((n) => n.id === nodeId);
  if (!node) return null;
  const type = node.data.triggerConfig?.type;

  if (!type) {
    return (
      <div className="space-y-3" data-testid="flow-trigger-unset">
        <p className="text-sm text-muted-foreground">
          Every flow starts with one thing that makes it run: a request from another app, a time you choose, or a change to your data.
        </p>
        {canManage ? (
          <Button type="button" className="w-full" data-testid="flow-trigger-choose" onClick={() => setChoosing(true)}>
            Choose what starts this flow
          </Button>
        ) : (
          <p className="text-xs text-muted-foreground">Nothing starts this flow yet. Ask a flow editor to choose.</p>
        )}
        <NodeSelectionModal
          open={choosing}
          mode="trigger"
          onClose={() => setChoosing(false)}
          onSaveTrigger={(config: TriggerConfig) => {
            updateNode(node.id, {
              data: {
                ...node.data,
                label: triggerLabel(config.type),
                icon: triggerOptions.find((t) => t.id === config.type)?.icon ?? 'Webhook',
                configured: true,
                triggerConfig: config,
              },
            });
            setChoosing(false);
          }}
        />
      </div>
    );
  }

  return (
    <Section title={triggerLabel(type)}>
      {type === 'webhook' ? <WebhookTriggerForm nodeId={nodeId} /> : type === 'schedule' ? <ScheduleTriggerForm nodeId={nodeId} /> : <DataTriggerForm nodeId={nodeId} />}
    </Section>
  );
}
