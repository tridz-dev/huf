import { memo, useState } from 'react';
import { useFlowPermissions } from '@/hooks/useFlowPermissions';
import { Handle, Position, NodeProps } from 'reactflow';
import {
  Play,
  Repeat,
  GitBranch,
  RotateCw,
  UserCheck,
  Code,
  Mail,
  Webhook,
  FileText,
  Calendar,
  Bot,
  Wrench,
  Trash2,
  Database,
  Save,
  FilePlus,
  Globe,
  MessageSquare,
  Sheet,
  AlertCircle,
  type LucideIcon,
} from 'lucide-react';
import { FlowNodeData } from '../../types/flow.types';
import { Card } from '../ui/card';
import { Button } from '../ui/button';
import { DeleteStepDialog } from '../flow/DeleteStepDialog';
import { useFlowContext } from '../../contexts/FlowContext';
import { Loader2, CheckCircle2, XCircle, Clock } from 'lucide-react';
import { NODE_CARD_BASE, NODE_HANDLE, NODE_ICON_WELL, getExecutionStatusClasses } from './nodeStyles';
import { cn } from '@/lib/utils';
import { actionHasConfiguredContent } from '../../lib/flowNodeConfigured';
import { branchHandlesFor, ROUTER_HANDLE } from '../../lib/flowBranches';
import { validateNode } from '../../lib/flowValidation';
import { unreachableNodeIds } from '../../lib/flowEdit';
import { toolLabel } from '../../lib/flowIntegrations';
import { NotConnected } from '../flow/NotConnected';

const iconMap: Record<string, LucideIcon> = {
  Play,
  Repeat,
  GitBranch,
  RotateCw,
  UserCheck,
  Code,
  Mail,
  Webhook,
  FileText,
  Calendar,
  Bot,
  Wrench,
  Database,
  Save,
  Trash2,
  FilePlus,
  Globe,
  MessageSquare,
  Sheet
};

type ActionNodeProps = NodeProps<FlowNodeData>;

export const ActionNode = memo(({ id, data, selected }: ActionNodeProps) => {
  const { deleteNode, activeFlow } = useFlowContext();
  const { canManage } = useFlowPermissions();
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const Icon = data.icon && iconMap[data.icon] ? iconMap[data.icon] : Play;
  const incomplete = validateNode({ id, data }, activeFlow?.edges ?? []);
  const orphaned = activeFlow ? unreachableNodeIds(activeFlow.nodes, activeFlow.edges).has(id) : false;
  const cfg = data.actionConfig as ({ type?: string } & Record<string, unknown>) | undefined;
  const handles = branchHandlesFor(cfg?.type, cfg);
  const isRouter = cfg?.type === 'router';
  const toolId = cfg?.type === 'tool-call' && typeof cfg.tool_id === 'string' && cfg.tool_id ? cfg.tool_id : undefined;
  const statusClasses = getExecutionStatusClasses(data.status, selected, { unconfigured: incomplete.length > 0 || orphaned });

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

  return (
    <div className="relative" data-testid={`flow-node-${id}`} data-node-type={cfg?.type} data-incomplete={incomplete.length > 0 ? 'true' : 'false'}>
      <Handle
        type="target"
        data-testid={`flow-handle-in-${id}`}
        position={Position.Top}
        className={NODE_HANDLE}
      />
      <Card className={cn(NODE_CARD_BASE, statusClasses)}>
        {canManage && selected && data.status !== 'running' && data.status !== 'waiting' && (
          <Button
            variant="ghost"
            size="icon"
            className="absolute top-2 right-2 h-7 w-7 text-muted-foreground hover:text-destructive hover:bg-destructive/10"
            onClick={handleDeleteClick}
            data-testid={`flow-node-delete-${id}`}
            aria-label="Delete step"
            title="Delete step"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </Button>
        )}
        <div className="flex items-center gap-3 pr-6">
          <div className={cn(NODE_ICON_WELL, 'text-ink relative')}>
            {data.status === 'running' ? (
              <Loader2 className="w-5 h-5 animate-spin" />
            ) : data.status === 'success' ? (
              <CheckCircle2 className="w-5 h-5 text-good" />
            ) : data.status === 'error' ? (
              <XCircle className="w-5 h-5 text-destructive" />
            ) : data.status === 'waiting' ? (
              <Clock className="w-5 h-5 text-signal" />
            ) : (
              <Icon className="w-5 h-5" />
            )}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5">
              <div className="text-sm font-medium min-w-0 text-card-foreground line-clamp-2 break-words leading-snug" title={data.label} data-testid={`flow-node-title-${id}`}>
                {data.label}
              </div>
              {incomplete.length > 0 && <AlertCircle className="w-4 h-4 text-signal shrink-0" aria-label="Needs setup" />}
            </div>
            {incomplete.length > 0 && (
              <div className="text-xs text-signal-ink" data-testid={`flow-node-incomplete-${id}`} title={incomplete[0]?.message ?? 'Select this step to set it up'}>Needs setup</div>
            )}
            {orphaned && (
              <div className="text-xs text-signal-ink" data-testid={`flow-node-orphan-${id}`}>Nothing leads to this step</div>
            )}
            {data.description && (
              <div className="text-xs text-muted-foreground">{data.description}</div>
            )}
            {toolId && toolLabel(toolId).toLowerCase() !== data.label.toLowerCase() && (
              <div className="text-xs text-muted-foreground truncate" title={toolLabel(toolId)} data-testid={`flow-node-tool-${id}`}>
                {toolLabel(toolId)}
              </div>
            )}
            {toolId && <NotConnected toolId={toolId} compact testIdSuffix={`node-${id}`} />}
          </div>
        </div>
      </Card>
      {handles.length > 0 ? (
        handles.map((h, i) => (
          <Handle
            key={h.route}
            id={h.handleId}
            type="source"
            position={Position.Bottom}
            style={{ left: `${((i + 1) / (handles.length + 1)) * 100}%` }}
            className={NODE_HANDLE}
            data-testid={`flow-handle-${id}-${h.route}`}
          >
            {/* Sit beside the dot, not under it, so the edge leaving the dot never runs through the text. */}
            <span
              className={cn(
                'pointer-events-none absolute top-2 whitespace-nowrap text-[10px] text-muted-foreground',
                i === 0 ? 'right-3' : i === handles.length - 1 ? 'left-3' : '-translate-x-1/2'
              )}
            >
              {h.label}
            </span>
          </Handle>
        ))
      ) : (
        <Handle id={isRouter ? ROUTER_HANDLE : undefined} type="source" position={Position.Bottom} className={NODE_HANDLE} data-testid={`flow-handle-${id}`} />
      )}

      <DeleteStepDialog nodeId={showDeleteConfirm ? id : null} onOpenChange={setShowDeleteConfirm} />
    </div>
  );
});

ActionNode.displayName = 'ActionNode';
