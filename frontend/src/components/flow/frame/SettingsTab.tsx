import { useEffect, useMemo, useState } from 'react';
import { ChevronRight } from 'lucide-react';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '../../ui/collapsible';
import { Input } from '../../ui/input';
import { Label } from '../../ui/label';
import { Textarea } from '../../ui/textarea';
import { JsonArea } from '../../common/JsonArea';
import { FieldHint } from '../FieldHint';
import { useFlowContext } from '../../../contexts/FlowContext';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { edgeRoute, serializeFlow } from '../../../services/flowSerializer';
import { getFlowTools } from '../../../services/toolApi';
import { nodeKind } from '@/lib/flow-graph/flowValidation';
import { cn } from '@/lib/utils';
import type { FlowNode } from '../../../types/flow.types';
import { FieldError } from '../forms/formKit';
import { ApprovalTimeoutField } from '../forms/approval/ApprovalTimeoutField';
import { Pressable } from './Pressable';

type Cfg = Record<string, unknown>;

/**
 * Settings tab: what to do if the step fails, how long to wait, a note, how later steps see this step, and the raw
 * step as JSON. Optional things only: a required field is never here (it is always in Setup).
 */
export function SettingsTab({ node }: { node: FlowNode }) {
  const { activeFlow, updateNodeData } = useFlowContext();
  const { canManage } = useFlowPermissions();
  const kind = nodeKind(node);
  const isAction = node.data.nodeType === 'action';
  const cfg = (node.data.actionConfig ?? {}) as Cfg;
  const type = String(cfg.type ?? '');
  const patchConfig = (p: Cfg) =>
    updateNodeData(node.id, (data) => {
      const next: Cfg = { ...(data.actionConfig as Cfg | undefined), ...p };
      for (const k of Object.keys(p)) if (p[k] === undefined) delete next[k];
      return { ...data, actionConfig: next } as FlowNode['data'];
    });

  const errorEdge = activeFlow?.edges.find((e) => e.source === node.id && edgeRoute(e) === 'error');
  const errorTarget = activeFlow?.nodes.find((n) => n.id === errorEdge?.target);

  const toolId = type === 'tool-call' ? String(cfg.tool_id ?? '') : '';
  const [isMcp, setIsMcp] = useState(false);
  useEffect(() => {
    if (!toolId) {
      setIsMcp(false);
      return;
    }
    let live = true;
    getFlowTools()
      .then((list) => live && setIsMcp((list || []).some((t) => t.name === toolId && t.source === 'mcp')))
      .catch(() => live && setIsMcp(false));
    return () => {
      live = false;
    };
  }, [toolId]);

  const toolSeconds = typeof cfg.timeout_ms === 'number' ? Math.round(cfg.timeout_ms / 1000) : '';
  const isWebRequest = type === 'tool-call' && toolId === 'http_request';
  const showToolTimeout = type === 'tool-call' && (isMcp || isWebRequest || toolSeconds !== '');

  return (
    <div className="space-y-5" data-testid="flow-settings-tab">
      {isAction && (
        <div data-testid="flow-settings-on-failure">
          <Label size="sm">If this step fails</Label>
          <p className="mt-1 text-xs" data-testid="flow-on-failure-value">
            {errorTarget ? `The flow carries on with "${errorTarget.data.label}".` : 'The flow stops and the run shows as failed.'}
          </p>
        </div>
      )}

      {showToolTimeout && (
        <div>
          <Label htmlFor="tool-timeout" size="sm">Stop waiting after (seconds)</Label>
          <Input
            id="tool-timeout"
            data-testid={`flow-field-${kind}-timeout_ms`}
            type="number"
            min={1}
            disabled={!canManage}
            value={toolSeconds}
            onChange={(e) => patchConfig({ timeout_ms: e.target.value === '' ? undefined : Math.max(1, parseInt(e.target.value, 10)) * 1000 })}
            placeholder={isWebRequest ? '30' : 'No limit'}
          />
          <FieldHint testId={`flow-field-${kind}-timeout_ms-help`}>
            {isWebRequest
              ? 'How long to wait for the website to answer before this step fails. Leave empty to wait up to 30 seconds.'
              : 'How long to wait for the connected tool to answer. Leave empty for no limit.'}
          </FieldHint>
          <FieldError nodeId={node.id} kind={kind} field="timeout_ms" />
        </div>
      )}

      {type === 'human.approval' && (
        <div>
          <ApprovalTimeoutField
            nodeId={node.id}
            kind={kind}
            timeoutMs={typeof cfg.timeout_ms === 'number' ? cfg.timeout_ms : undefined}
            onChange={(ms) => patchConfig({ timeout_ms: ms })}
            disabled={!canManage}
          />
          <FieldError nodeId={node.id} kind={kind} field="timeout_ms" />
        </div>
      )}

      <div>
        <Label htmlFor="step-notes" size="sm">Notes</Label>
        <Textarea
          id="step-notes"
          data-testid="flow-step-notes"
          disabled={!canManage}
          value={node.data.notes ?? ''}
          onChange={(e) => updateNodeData(node.id, (data) => ({ ...data, notes: e.target.value || undefined }))}
          placeholder="Why this step exists, or what to remember about it"
          className="min-h-20"
        />
        <FieldHint>Only people editing the flow see this. It never changes what the flow does.</FieldHint>
      </div>

      <div data-testid="flow-step-reference-name">
        <Label size="sm">Name in data lists</Label>
        <p className="mt-1 break-words text-xs">{node.data.label || 'This step'}</p>
        <FieldHint>Later steps find this step's data under this name. Rename the step at the top to change it.</FieldHint>
      </div>

      <ViewAsJson node={node} />
    </div>
  );
}

function ViewAsJson({ node }: { node: FlowNode }) {
  const { activeFlow } = useFlowContext();
  const [open, setOpen] = useState(false);
  const json = useMemo(() => {
    if (!open || !activeFlow) return '';
    try {
      const graph = serializeFlow(activeFlow);
      const found = graph.nodes.find((n) => n.id === node.id);
      return found ? JSON.stringify(found, null, 2) : '';
    } catch {
      return '';
    }
  }, [open, activeFlow, node.id]);
  return (
    <Collapsible open={open} onOpenChange={setOpen} data-testid="flow-view-as-json">
      <CollapsibleTrigger asChild data-testid="flow-view-as-json-toggle">
        <Pressable className="flex min-h-8 w-full items-center gap-1 rounded-md text-left text-xs font-medium text-muted-foreground hover:text-foreground">
          <ChevronRight className={cn('h-3.5 w-3.5 transition-transform', open && 'rotate-90')} aria-hidden />
          Advanced
        </Pressable>
      </CollapsibleTrigger>
      <CollapsibleContent className="mt-2">
        <JsonArea
          surfaceKey="step-stored"
          title="This step as the flow stores it (JSON)"
          help="For people who work with JSON. It is only here to read and copy: to change the step, use the Setup tab. Nothing you do here changes the flow."
          value={json}
          readOnly
          textTestId="flow-view-as-json-text"
        />
      </CollapsibleContent>
    </Collapsible>
  );
}
