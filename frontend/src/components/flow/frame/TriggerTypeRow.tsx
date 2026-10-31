import { useState } from 'react';
import { Edit } from 'lucide-react';
import { Button } from '../../ui/button';
import { Label } from '../../ui/label';
import { NodeSelectionModal } from '../../modals/NodeSelectionModal';
import { useFlowContext } from '../../../contexts/FlowContext';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { triggerLabel } from '@/lib/flow/flowLabels';
import type { FlowNode, TriggerConfig } from '../../../types/flow.types';

const TRIGGER_ICONS: Record<string, string> = { webhook: 'Webhook', schedule: 'Clock', 'doc-event': 'Database' };

/** Which trigger starts the flow, with the button to change it. An unset trigger shows nothing here: the form below holds the one button to choose. */
export function TriggerTypeRow({ node }: { node: FlowNode }) {
  const { updateNode } = useFlowContext();
  const { canManage } = useFlowPermissions();
  const [choosing, setChoosing] = useState(false);
  const type = node.data.triggerConfig?.type;

  return (
    <>
      {type ? (
        <div className="flex items-center justify-between gap-2">
          <div className="min-w-0">
            <Label size="sm">Starts when</Label>
            <div className="mt-0.5 truncate text-sm" data-testid="flow-trigger-type">{triggerLabel(type)}</div>
          </div>
          {canManage && (
            <Button variant="outline" size="sm" data-testid="flow-trigger-change" onClick={() => setChoosing(true)}>
              <Edit className="mr-1 h-3 w-3" />
              Change
            </Button>
          )}
        </div>
      ) : null}
      <NodeSelectionModal
        open={choosing}
        mode="trigger"
        onClose={() => setChoosing(false)}
        onSaveTrigger={(config: TriggerConfig) => {
          updateNode(node.id, {
            data: {
              ...node.data,
              label: triggerLabel(config.type),
              icon: TRIGGER_ICONS[config.type || 'webhook'],
              configured: true,
              triggerConfig: config,
            },
          });
          setChoosing(false);
        }}
        initialTriggerConfig={node.data.triggerConfig}
      />
    </>
  );
}
