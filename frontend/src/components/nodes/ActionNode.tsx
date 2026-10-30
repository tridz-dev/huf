import { memo, useState } from 'react';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { Handle, Position, NodeProps } from 'reactflow';
import { FlowNodeData } from '../../types/flow.types';
import { DeleteStepDialog } from '../flow/DeleteStepDialog';
import { useFlowContext } from '../../contexts/FlowContext';
import { NODE_HANDLE, getExecutionStatusClasses, handleSpread } from './nodeStyles';
import { actionHasConfiguredContent } from '../../lib/flow/flowNodeConfigured';
import { branchHandlesFor, ROUTER_HANDLE } from '../../lib/flow/flowBranches';
import { validateNode } from '../../lib/flow-graph/flowValidation';
import { orphanNote } from '../../lib/flow-graph/flowCanvasGraph';
import { connectPath, integrationForTool, isToolUnconnected, useIntegrationStatus } from '../../lib/flow/flowIntegrations';
import { actionSubtitle, cardStatus } from '../../lib/flow/flowNodeCard';
import { cardIcon } from './nodeIcons';
import { CardStatusLine, ConnectLink, NodeCard } from './NodeCard';

type ActionNodeProps = NodeProps<FlowNodeData>;

export const ActionNode = memo(({ id, data, selected }: ActionNodeProps) => {
  const { deleteNode, activeFlow } = useFlowContext();
  const { canManage } = useFlowPermissions();
  const integrationStatus = useIntegrationStatus();
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const incomplete = validateNode({ id, data }, activeFlow?.edges ?? []);
  // Only a step with no line into it: one with a line from a cut-off part is not "nothing leads here".
  const orphaned = activeFlow ? orphanNote(id, activeFlow.nodes, activeFlow.edges) === 'Nothing leads to this step' : false;
  const cfg = data.actionConfig as ({ type?: string } & Record<string, unknown>) | undefined;
  const handles = branchHandlesFor(cfg?.type, cfg);
  const isRouter = cfg?.type === 'router';
  const toolId = cfg?.type === 'tool-call' && typeof cfg.tool_id === 'string' && cfg.tool_id ? cfg.tool_id : undefined;
  const service = integrationForTool(toolId);
  const status = cardStatus({
    runStatus: data.status,
    incomplete: incomplete.length > 0,
    orphaned,
    notConnected: isToolUnconnected(toolId, integrationStatus),
  });
  const frameClass = getExecutionStatusClasses(data.status, selected, { unconfigured: incomplete.length > 0 || orphaned });

  // Confirm only when the node has real config; a picked-but-blank node deletes
  // immediately (see actionHasConfiguredContent).
  const handleDeleteClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (actionHasConfiguredContent(data)) {
      setShowDeleteConfirm(true);
    } else {
      deleteNode(id);
    }
  };

  const canDelete = canManage && selected && data.status !== 'running' && data.status !== 'waiting';
  return (
    <div className={data.disabled ? 'relative opacity-60' : 'relative'} data-disabled={data.disabled ? 'true' : undefined} title={data.disabled ? 'Turned off: the flow skips this step' : undefined} data-testid={`flow-node-${id}`} data-node-type={cfg?.type} data-incomplete={incomplete.length > 0 ? 'true' : 'false'}>
      <Handle
        type="target"
        data-testid={`flow-handle-in-${id}`}
        position={Position.Top}
        className={NODE_HANDLE}
      />
      <NodeCard
        id={id}
        icon={cardIcon(data)}
        title={data.label}
        subtitle={actionSubtitle(data.actionConfig)}
        status={status}
        runSummary={data.runSummary}
        frameClass={frameClass}
        onDelete={canDelete ? handleDeleteClick : undefined}
        deleteLabel="Delete step"
        footer={
          <CardStatusLine
            id={id}
            status={status}
            title={status.kind === 'needs-setup' ? incomplete[0]?.message ?? 'Select this step to set it up' : undefined}
            action={
              status.kind === 'not-connected' && service && canManage ? (
                <span data-testid={`flow-not-connected-node-${id}`} className="contents">
                  <ConnectLink
                    to={connectPath(service)}
                    label="Connect"
                    ariaLabel={`Connect ${integrationStatus[service]?.label ?? service}`}
                    testId={`flow-connect-link-node-${id}`}
                  />
                </span>
              ) : undefined
            }
          />
        }
      />
      {handles.length > 0 ? (
        handles.map((h, i) => (
          <Handle
            key={h.route}
            id={h.handleId}
            type="source"
            position={Position.Bottom}
            style={handleSpread(i, handles.length)}
            className={NODE_HANDLE}
            data-testid={`flow-handle-${id}-${h.route}`}
            title={`${h.label}: drag from here to connect`}
          />
        ))
      ) : (
        <Handle id={isRouter ? ROUTER_HANDLE : undefined} type="source" position={Position.Bottom} className={NODE_HANDLE} data-testid={`flow-handle-${id}`} />
      )}

      <DeleteStepDialog nodeId={showDeleteConfirm ? id : null} onOpenChange={setShowDeleteConfirm} />
    </div>
  );
});

ActionNode.displayName = 'ActionNode';
