import { useEffect, useMemo, useRef, useState } from 'react';
import { Unlink } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useFlowContext } from '../../../contexts/FlowContext';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { FlowValueInput } from '../../FlowValueInput';
import { ActionConfigForm, TriggerConfigForm } from '../NodeConfigForms';
import { nodeKind } from '@/lib/flow-graph/flowValidation';
import type { FlowNode, FlowNodeData } from '../../../types/flow.types';
import { ConnectionPanel } from './ConnectionPanel';
import { clearFocusRequest, requestFocus, useFrame } from './frameStore';
import { issueTab, issuesForStep, tabsFor, type FrameTab } from './frameIssues';
import { focusFieldIn } from './focusField';
import { SettingsTab } from './SettingsTab';
import { StatusStrip } from './StatusStrip';
import { StepHeader } from './StepHeader';
import { StepTestPlaceholder } from './TestTab';
import { TriggerTypeRow } from './TriggerTypeRow';
import { useFlowIssues } from './useFlowIssues';

const TAB_LABEL: Record<FrameTab, string> = { setup: 'Setup', test: 'Test', settings: 'Settings' };

/**
 * The step panel: sticky header (name, kind, menu, close), status strip, tabs, then the tab's body. All three
 * bodies stay mounted (inactive ones are hidden) so a half-typed field and the "(i)" text survive a tab change.
 */
export function StepFrame({ node, onClose, onDelete }: { node: FlowNode; onClose?: () => void; onDelete: () => void }) {
  const { updateNodeData } = useFlowContext();
  const { canManage } = useFlowPermissions();
  const issues = useFlowIssues();
  const mine = useMemo(() => issuesForStep(issues, node.id), [issues, node.id]);
  const kind = nodeKind(node);
  const tabs = tabsFor(node);
  const [tab, setTab] = useState<FrameTab>('setup');
  const body = useRef<HTMLDivElement>(null);
  const request = useFrame((s) => s.focusRequest);
  const count = (t: FrameTab) => mine.filter((i) => issueTab(i) === t).length;

  // A different step or flow: back to Setup.
  useEffect(() => setTab('setup'), [node.id]);

  // "Fix" in the checklist and the status strip ask for a field: open its tab, then scroll to it and focus it.
  useEffect(() => {
    if (!request || request.nodeId !== node.id) return;
    const issue = mine.find((i) => i.field === request.field) ?? { field: request.field };
    setTab(issueTab(issue));
    let frames = 0;
    let raf = 0;
    const attempt = () => {
      if (body.current && focusFieldIn(body.current, kind, request.field)) return clearFocusRequest(request.seq);
      if (++frames > 20) {
        body.current?.scrollTo({ top: 0, behavior: 'smooth' });
        return clearFocusRequest(request.seq);
      }
      raf = requestAnimationFrame(attempt);
    };
    raf = requestAnimationFrame(attempt);
    return () => cancelAnimationFrame(raf);
  }, [request, node.id, kind, mine]);

  const jump = () => {
    const first = mine[0];
    if (!first) return;
    setTab(issueTab(first));
    requestFocus(node.id, first.field);
  };

  const orphan = mine.find((i) => i.field === 'connection');
  const tabIds = useMemo(() => Object.fromEntries(tabs.map((t) => [t, `step-tab-${t}`])), [tabs]);

  return (
    <div className="flex min-h-0 flex-1 flex-col" data-testid="flow-step-frame" data-step-kind={kind}>
      <StepHeader node={node} onClose={onClose} onDelete={onDelete} />
      {canManage && <StatusStrip count={mine.length} disabled={node.data.disabled} onJump={jump} />}
      {tabs.length > 1 && (
        <div role="tablist" aria-label="Step sections" className="flex h-10 shrink-0 items-end gap-5 border-b border-border px-3.5" data-testid="flow-sidebar-tabs">
          {tabs.map((t) => (
            <button
              key={t}
              id={tabIds[t]}
              role="tab"
              type="button"
              aria-selected={tab === t}
              aria-controls={`${tabIds[t]}-panel`}
              data-testid={`flow-sidebar-tab-${t}`}
              onClick={() => setTab(t)}
              className={cn(
                'relative -mb-px flex h-9 items-center gap-1.5 border-b-2 px-0.5 text-ui-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                tab === t ? 'border-signal font-semibold text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground'
              )}
            >
              {TAB_LABEL[t]}
              {count(t) > 0 && <span className="h-1.5 w-1.5 rounded-full bg-warning" aria-label={`${count(t)} to finish`} data-testid={`flow-sidebar-tab-${t}-dot`} />}
            </button>
          ))}
        </div>
      )}
      <div ref={body} className="min-h-0 flex-1 overflow-y-auto p-3.5">
        <fieldset disabled={!canManage} className="contents">
          <div role="tabpanel" id={`${tabIds.setup}-panel`} aria-labelledby={tabIds.setup} hidden={tab !== 'setup'} className="space-y-4" data-testid="flow-tab-setup">
            {orphan && (
              <div role="status" className="flex items-start gap-2 rounded-md border border-warning/30 bg-warning-tint p-2.5 text-xs text-warning" data-testid="flow-node-orphan-note">
                <Unlink className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
                <span>{orphan.message}</span>
              </div>
            )}
            {node.data.nodeType === 'trigger' && (
              <>
                <TriggerTypeRow node={node} />
                <TriggerConfigForm key={node.id} nodeId={node.id} />
              </>
            )}
            {node.data.nodeType === 'action' && (
              <>
                <ConnectionPanel toolId={toolIdOf(node)} />
                <ActionConfigForm key={node.id} nodeId={node.id} />
              </>
            )}
            {node.data.nodeType === 'end' && (
              <div key={node.id}>
                <FlowValueInput
                  id="end-value"
                  nodeId={node.id}
                  testId="flow-field-output-value"
                  label="Result"
                  optional
                  hint="Shown in run details as what the flow produced. Leave it empty if you do not need a result."
                  value={node.data.endConfig?.value}
                  onChange={(v) => updateNodeData(node.id, (data) => ({ ...data, endConfig: { value: v } }) as FlowNodeData)}
                />
              </div>
            )}
          </div>
          {tabs.includes('test') && (
            <div role="tabpanel" id={`${tabIds.test}-panel`} aria-labelledby={tabIds.test} hidden={tab !== 'test'} data-testid="flow-tab-test">
              <StepTestPlaceholder nodeId={node.id} isTrigger={node.data.nodeType === 'trigger'} />
            </div>
          )}
          {tabs.includes('settings') && (
            <div role="tabpanel" id={`${tabIds.settings}-panel`} aria-labelledby={tabIds.settings} hidden={tab !== 'settings'} data-testid="flow-tab-settings">
              <SettingsTab node={node} />
            </div>
          )}
        </fieldset>
      </div>
    </div>
  );
}

function toolIdOf(node: FlowNode): string | undefined {
  const cfg = node.data.actionConfig as { type?: string; tool_id?: unknown } | undefined;
  return cfg?.type === 'tool-call' && typeof cfg.tool_id === 'string' && cfg.tool_id ? cfg.tool_id : undefined;
}
