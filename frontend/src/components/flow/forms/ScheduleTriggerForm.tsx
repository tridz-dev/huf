import { ScheduleEditor } from '../ScheduleEditor';
import { useFlowContext } from '@/contexts/FlowContext';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { type FlowNodeData, type ScheduleTriggerConfig } from '@/types/flow.types';

/**
 * The schedule picker wired to the node. Edits go straight into the flow (no typing delay), so what the summary and the
 * step card say is always what the picker shows, and a corrected pattern clears its message at once.
 */
export function ScheduleTriggerForm({ nodeId }: { nodeId: string }) {
  const { activeFlow, updateNodeData } = useFlowContext();
  const { canManage } = useFlowPermissions();
  const config = activeFlow?.nodes.find((n) => n.id === nodeId)?.data.triggerConfig as ScheduleTriggerConfig | undefined;

  const write = (change: Partial<ScheduleTriggerConfig>) =>
    updateNodeData(nodeId, (data) => {
      const next = { ...(data.triggerConfig as ScheduleTriggerConfig), ...change };
      for (const key of Object.keys(change) as Array<keyof ScheduleTriggerConfig>) if (change[key] === undefined) delete next[key];
      return { ...data, triggerConfig: next } as FlowNodeData;
    });

  return (
    <ScheduleEditor
      cron={config?.cron}
      timeZone={config?.time_zone}
      disabled={!canManage}
      onChange={(cron) => write({ cron })}
      onZoneChange={(time_zone) => write({ time_zone })}
    />
  );
}
