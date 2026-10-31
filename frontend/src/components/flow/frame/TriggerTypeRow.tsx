import { useState } from 'react';
import { Edit } from 'lucide-react';
import { Button } from '../../ui/button';
import { Label } from '../../ui/label';
import { NodeSelectionModal } from '../../modals/NodeSelectionModal';
import { useFlowContext } from '../../../contexts/FlowContext';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { triggerLabel, triggerStepFields } from '@/lib/flow/flowLabels';
import type { FlowNode, TriggerConfig } from '../../../types/flow.types';

/** Which trigger starts the flow, with the button to change it. An unset trigger asks for a choice instead. */
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
      ) : (
        <div className="space-y-2 rounded-md border border-dashed border-border p-3">
          <div className="text-sm" data-testid="flow-trigger-type">
            <span className="text-muted-foreground">Not set up yet</span>
          </div>
          <p className="text-meta leading-snug text-muted-foreground" data-testid="flow-hint-trigger-type">
            The trigger decides when the flow starts. Choose one to continue.
          </p>
          {canManage && (
            <Button size="sm" data-testid="flow-trigger-change" onClick={() => setChoosing(true)}>
              Choose a trigger
            </Button>
          )}
        </div>
      )}
      <NodeSelectionModal
        open={choosing}
        mode="trigger"
        onClose={() => setChoosing(false)}
        onSaveTrigger={(config: TriggerConfig) => {
          updateNode(node.id, {
            data: {
              ...node.data,
              ...triggerStepFields(config),
            },
          });
          setChoosing(false);
        }}
        initialTriggerConfig={node.data.triggerConfig}
      />
    </>
  );
}
