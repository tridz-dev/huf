import { useState } from 'react';
import { X, Settings, Edit, Trash2, AlertCircle } from 'lucide-react';
import { Input } from './ui/input';
import { Button } from './ui/button';
import { Label } from './ui/label';
import { cn } from '@/lib/utils';
import { DeleteStepDialog } from './flow/DeleteStepDialog';
import { useFlowContext } from '../contexts/FlowContext';
import { NodeSelectionModal } from './modals/NodeSelectionModal';
import { ActionConfigForm, TriggerConfigForm } from './flow/NodeConfigForms';
import { FlowValueInput } from './FlowValueInput';
import { edgeRoute } from '../services/flowSerializer';
import { validateNode } from '@/lib/flow-graph/flowValidation';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { triggerLabel } from '@/lib/flow/flowLabels';
import { STEP_NEEDS_HINT } from '@/lib/flow/flowHelp';
import type { FlowNodeData, TriggerConfig } from '../types/flow.types';

interface RightSidebarProps {
  onToggle: () => void;
  variant?: 'panel' | 'sheet';
}

const TRIGGER_ICONS: Record<string, string> = { webhook: 'Webhook', schedule: 'Clock', 'doc-event': 'Database' };

const ROUTE_TEXT: Record<string, string> = {
  next: 'Runs next',
  error: 'Runs if the step fails',
  true: 'Runs when the condition is true',
  false: 'Runs when the condition is false',
  option: 'A path the AI can choose',
  default: 'Used when nothing else matches',
  approve: 'Runs when approved',
  reject: 'Runs when rejected',
  timeout: 'Runs when nobody answers in time',
  body: 'Runs once for each item',
};

export function RightSidebar({ onToggle, variant = 'panel' }: RightSidebarProps) {
  const { activeFlow, selectedNodeId, selectedEdgeId, updateNode, updateNodeData, updateEdges } = useFlowContext();
  const selectedNode = activeFlow?.nodes.find((n) => n.id === selectedNodeId);
  const selectedEdge = activeFlow?.edges.find((e) => e.id === selectedEdgeId);
  const { canManage } = useFlowPermissions();
  const [isChangingTrigger, setIsChangingTrigger] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const isSheet = variant === 'sheet';
  const issues = selectedNode ? validateNode(selectedNode, activeFlow?.edges ?? []) : [];
  const nodeKindLabel = selectedNode?.data.nodeType === 'trigger' ? 'Trigger' : selectedNode?.data.nodeType === 'end' ? 'End' : 'Step';

  return (
    <div
      data-testid="flow-config-sidebar"
      className={cn('relative bg-card flex flex-col', isSheet ? 'w-full max-w-full' : 'w-[300px] border-l border-border', 'h-full')}
    >
      {!canManage && (selectedNode || selectedEdge) && (
        <div role="status" className="shrink-0 border-b border-border bg-muted px-3.5 py-2 text-xs text-muted-foreground" data-testid="flow-view-only-banner">
          You have view-only access to this flow
        </div>
      )}
      <div className="flex-1 overflow-y-auto p-3.5 space-y-3.5">
        <fieldset disabled={!canManage} className="contents">
        {!selectedNode && !selectedEdge ? (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <Settings className="w-12 h-12 text-muted-foreground mb-4" />
            <div className="text-sm text-muted-foreground">Select a step or a connection to see its settings</div>
            <p className="mt-2 max-w-[240px] text-xs text-muted-foreground" data-testid="flow-sidebar-empty-hint">
              Click a step on the canvas to set it up. A step marked "Needs setup" still has something missing. Click a line to see what it means.
            </p>
          </div>
        ) : selectedEdge ? (
          <div className="space-y-3" data-testid="flow-edge-config">
            <div className="text-sm font-semibold">Connection</div>
            <p className="text-xs text-muted-foreground" data-testid="flow-edge-meaning">
              {ROUTE_TEXT[edgeRoute(selectedEdge)] ?? 'Connection'}
            </p>
            {edgeRoute(selectedEdge) === 'option' ? (
              <div>
                <Label htmlFor="edge-label" size="sm">Path name</Label>
                <Input
                  id="edge-label"
                  data-testid="flow-edge-label"
                  value={(selectedEdge.label as string) || ''}
                  onChange={(e) =>
                    activeFlow && updateEdges(activeFlow.edges.map((edge) => (edge.id === selectedEdge.id ? { ...edge, label: e.target.value } : edge)))
                  }
                  placeholder="For example: urgent"
                />
                <p className="text-[11px] text-muted-foreground mt-1">The AI picks the path whose name fits best.</p>
              </div>
            ) : null}
          </div>
        ) : selectedNode ? (
          <>
            <div className="sticky -top-3.5 z-10 bg-card -mx-3.5 -mt-3.5 mb-0 h-10 px-3.5 flex items-center gap-2 border-b border-border shrink-0">
              <span className="text-[13px] leading-none truncate" style={{ fontWeight: 590 }} title={selectedNode.data.label} data-testid="flow-sidebar-title">
                {selectedNode.data.label}
              </span>
              <span className="font-mono text-[10px] uppercase tracking-wide text-muted-foreground bg-muted px-1.5 py-0.5 rounded shrink-0">
                {nodeKindLabel}
              </span>
              <div className="flex-1" />
              {canManage && (
                <Button variant="ghost" size="icon-sm" aria-label="Delete step" data-testid="flow-sidebar-delete" className="text-muted-foreground hover:text-destructive" onClick={() => setShowDeleteConfirm(true)}>
                  <Trash2 className="w-3.5 h-3.5" />
                </Button>
              )}
              {!isSheet && (
                <Button variant="ghost" size="icon-sm" aria-label="Close settings" data-testid="flow-sidebar-close" className="hover:bg-accent" onClick={onToggle}>
                  <X className="w-3.5 h-3.5 text-muted-foreground" />
                </Button>
              )}
            </div>

            {canManage && issues.length > 0 && (
              <div role="status" className="flex items-start gap-2 rounded-md border border-signal/40 bg-signal/5 p-2 text-xs" data-testid="flow-node-incomplete">
                <AlertCircle className="w-4 h-4 text-signal shrink-0" />
                <span>Finish setting up {selectedNode.data.label}: {issues[0].message}{issues.length > 1 ? ` (${issues.length - 1} more)` : ''}</span>
              </div>
            )}

            <div>
              <Label htmlFor="node-title">Step name</Label>
              <Input
                id="node-title"
                data-testid="flow-node-title-input"
                value={selectedNode.data.label}
                onChange={(e) => updateNodeData(selectedNode.id, (data) => ({ ...data, label: e.target.value }))}
                className="font-medium"
              />
              <p className="mt-1 text-[11px] leading-snug text-muted-foreground" data-testid="flow-hint-step-name">A name that says what this step does. It shows on the canvas and in run details.</p>
            </div>

            <div className="border-t border-border" />

            {selectedNode.data.nodeType === 'trigger' && (
              <>
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <Label>Trigger type</Label>
                    {canManage && (
                      <Button variant="ghost" size="sm" data-testid="flow-trigger-change" onClick={() => setIsChangingTrigger(true)}>
                        <Edit className="w-3 h-3 mr-1" />
                        Change
                      </Button>
                    )}
                  </div>
                  <div className="p-2 rounded-md bg-muted text-sm" data-testid="flow-trigger-type">
                    {selectedNode.data.triggerConfig?.type ? (
                      triggerLabel(selectedNode.data.triggerConfig.type)
                    ) : (
                      <span className="text-muted-foreground">Not set up yet</span>
                    )}
                  </div>
                  {!selectedNode.data.triggerConfig?.type && (
                    <p className="mt-1 text-[11px] leading-snug text-muted-foreground" data-testid="flow-hint-trigger-type">
                      The trigger decides when the flow starts. Use Change to choose one.
                    </p>
                  )}
                </div>
                <TriggerConfigForm key={selectedNode.id} nodeId={selectedNode.id} />
              </>
            )}

            {selectedNode.data.nodeType === 'action' && (
              <>
                <ActionConfigForm key={selectedNode.id} nodeId={selectedNode.id} />
                <p className="border-t border-border pt-2 text-[11px] leading-snug text-muted-foreground" data-testid="flow-hint-step-result">{STEP_NEEDS_HINT}</p>
              </>
            )}

            {selectedNode.data.nodeType === 'end' && (
              <div className="space-y-3" key={selectedNode.id}>
                <Label weight="semibold" className="block" data-testid="flow-config-title">End</Label>
                <p className="text-xs text-muted-foreground">The flow finishes here. The value below is returned as the flow's result and shown in run details. Leave it empty if you do not need a result.</p>
                <FlowValueInput
                  id="end-value"
                  nodeId={selectedNode.id}
                  testId="flow-field-output-value"
                  label="Result"
                  optional
                  value={selectedNode.data.endConfig?.value}
                  onChange={(v) => updateNodeData(selectedNode.id, (data) => ({ ...data, endConfig: { value: v } }) as FlowNodeData)}
                />
              </div>
            )}
          </>
        ) : null}
        </fieldset>
      </div>

      <DeleteStepDialog nodeId={showDeleteConfirm ? selectedNodeId : null} onOpenChange={setShowDeleteConfirm} />

      {selectedNode && (
        <NodeSelectionModal
          open={isChangingTrigger}
          mode="trigger"
          onClose={() => setIsChangingTrigger(false)}
          onSaveTrigger={(config: TriggerConfig) => {
            updateNode(selectedNode.id, {
              data: {
                ...selectedNode.data,
                label: triggerLabel(config.type),
                icon: TRIGGER_ICONS[config.type || 'webhook'],
                configured: true,
                triggerConfig: config,
              },
            });
            setIsChangingTrigger(false);
          }}
          initialTriggerConfig={selectedNode.data.triggerConfig}
        />
      )}
    </div>
  );
}
