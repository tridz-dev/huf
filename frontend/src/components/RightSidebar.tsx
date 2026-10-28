import { useState } from 'react';
import { X, Settings, Edit, Trash2, AlertCircle } from 'lucide-react';
import { Input } from './ui/input';
import { Button } from './ui/button';
import { Label } from './ui/label';
import { cn } from '@/lib/utils';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from './ui/alert-dialog';
import { useFlowContext } from '../contexts/FlowContext';
import { NodeSelectionModal } from './modals/NodeSelectionModal';
import { ActionConfigForm, TriggerConfigForm } from './flow/NodeConfigForms';
import { FlowValueInput } from './FlowValueInput';
import { edgeRoute } from '../services/flowSerializer';
import { validateNode } from '@/lib/flowValidation';
import { triggerLabel } from '@/lib/flowLabels';
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
  branch: 'Runs in parallel',
};

export function RightSidebar({ onToggle, variant = 'panel' }: RightSidebarProps) {
  const { activeFlow, selectedNodeId, selectedEdgeId, updateNode, deleteNode, updateEdges } = useFlowContext();
  const selectedNode = activeFlow?.nodes.find((n) => n.id === selectedNodeId);
  const selectedEdge = activeFlow?.edges.find((e) => e.id === selectedEdgeId);
  const [isChangingTrigger, setIsChangingTrigger] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const isSheet = variant === 'sheet';
  const issues = selectedNode ? validateNode(selectedNode, activeFlow?.edges ?? []) : [];
  const nodeKindLabel = selectedNode?.data.nodeType === 'trigger' ? 'Trigger' : selectedNode?.data.nodeType === 'end' ? 'End' : 'Step';

  return (
    <div
      data-testid="flow-config-sidebar"
      className={cn('relative bg-card flex flex-col w-[300px]', 'h-full', !isSheet \&\& 'border-l border-border')}
    >
      <div className="flex-1 overflow-y-auto p-3.5 space-y-3.5">
        {!selectedNode && !selectedEdge ? (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <Settings className="w-12 h-12 text-muted-foreground mb-4" />
            <div className="text-sm text-muted-foreground">Select a step or a connection to see its settings</div>
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
            <div className="-mx-3.5 -mt-3.5 mb-0 h-10 px-3.5 flex items-center gap-2 border-b border-border shrink-0">
              <span className="text-[13px] leading-none truncate" style={{ fontWeight: 590 }} data-testid="flow-sidebar-title">
                {selectedNode.data.label}
              </span>
              <span className="font-mono text-[10px] uppercase tracking-wide text-muted-foreground bg-muted px-1.5 py-0.5 rounded shrink-0">
                {nodeKindLabel}
              </span>
              <div className="flex-1" />
              <Button variant="ghost" size="icon-sm" aria-label="Delete step" data-testid="flow-sidebar-delete" className="text-muted-foreground hover:text-destructive" onClick={() => setShowDeleteConfirm(true)}>
                <Trash2 className="w-3.5 h-3.5" />
              </Button>
              <Button variant="ghost" size="icon-sm" aria-label="Close settings" data-testid="flow-sidebar-close" className="hover:bg-accent" onClick={onToggle}>
                <X className="w-3.5 h-3.5 text-muted-foreground" />
              </Button>
            </div>

            {issues.length > 0 && (
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
                onChange={(e) => updateNode(selectedNode.id, { data: { ...selectedNode.data, label: e.target.value } })}
                className="font-medium"
              />
            </div>

            <div className="border-t border-border" />

            {selectedNode.data.nodeType === 'trigger' && (
              <>
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <Label>Trigger type</Label>
                    <Button variant="ghost" size="sm" data-testid="flow-trigger-change" onClick={() => setIsChangingTrigger(true)}>
                      <Edit className="w-3 h-3 mr-1" />
                      Change
                    </Button>
                  </div>
                  <div className="p-2 rounded-md bg-muted text-sm" data-testid="flow-trigger-type">
                    {selectedNode.data.triggerConfig?.type ? (
                      triggerLabel(selectedNode.data.triggerConfig.type)
                    ) : (
                      <span className="text-muted-foreground">Not set up yet</span>
                    )}
                  </div>
                </div>
                <TriggerConfigForm nodeId={selectedNode.id} />
              </>
            )}

            {selectedNode.data.nodeType === 'action' && <ActionConfigForm nodeId={selectedNode.id} />}

            {selectedNode.data.nodeType === 'end' && (
              <div className="space-y-3">
                <Label weight="semibold" className="block" data-testid="flow-config-title">End</Label>
                <p className="text-xs text-muted-foreground">The flow finishes here. The value below is returned as its result.</p>
                <FlowValueInput
                  id="end-value"
                  testId="flow-field-output-value"
                  label="Result"
                  optional
                  value={selectedNode.data.endConfig?.value}
                  onChange={(v) => updateNode(selectedNode.id, { data: { ...selectedNode.data, endConfig: { value: v } } as FlowNodeData })}
                />
              </div>
            )}
          </>
        ) : null}
      </div>

      <AlertDialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this step?</AlertDialogTitle>
            <AlertDialogDescription>The step and its connections will be removed.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="flow-delete-cancel">Cancel</AlertDialogCancel>
            <AlertDialogAction
              data-testid="flow-delete-confirm"
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => {
                if (selectedNodeId) {
                  deleteNode(selectedNodeId);
                  setShowDeleteConfirm(false);
                  onToggle();
                }
              }}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

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
