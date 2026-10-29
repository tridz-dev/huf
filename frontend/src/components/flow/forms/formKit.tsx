import { type ReactNode, useCallback, useEffect, useRef, useState } from 'react';
import { Label } from '../../ui/label';
import { Textarea } from '../../ui/textarea';
import { VariablePicker } from '../../ui/VariablePicker';
import { branchHandlesFor } from '@/lib/flow/flowBranches';
import { edgeRoute } from '../../../services/flowSerializer';
import { nodeKind, validateNode } from '@/lib/flow-graph/flowValidation';
import { type FlowNodeData } from '../../../types/flow.types';
import { useFlowContext } from '../../../contexts/FlowContext';

export type Cfg = Record<string, unknown>;
export type Opt = { value: string; label: string };

export const asObj = (v: unknown): Cfg => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Cfg) : {});
export const str = (v: unknown): string => (typeof v === 'string' ? v : '');

export interface FormShell {
  kind: string;
  error: (field: string) => string | undefined;
  /** Required-field message under a control. */
  Err: (props: { field: string }) => ReactNode;
}


/** How long typing may pause before an edit is written to the flow. Keeps a fast typist from re-rendering the whole canvas on every key. */
const COMMIT_DELAY_MS = 200;

/**
 * Shared hook: current node, its config, a merge-patch writer and the inline-error helper.
 * Edits show up in the form at once (local draft) and reach the flow after a short pause, on blur and on unmount.
 */
export function useNodeForm(nodeId: string, slot: 'triggerConfig' | 'actionConfig') {
  const { activeFlow, updateNodeData, getNode } = useFlowContext();
  const node = activeFlow?.nodes.find((n) => n.id === nodeId);
  const edges = activeFlow?.edges ?? [];
  const draftRef = useRef<{ nodeId: string; cfg: Cfg } | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [, rerender] = useState(0);

  const commit = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    const draft = draftRef.current;
    if (!draft) return;
    draftRef.current = null;
    updateNodeData(draft.nodeId, (data) => ({ ...data, [slot]: draft.cfg }) as FlowNodeData);
  }, [updateNodeData, slot]);

  // Write any pending edit when focus leaves a field (so Save/Run right after typing see it) and when this form goes away.
  useEffect(() => {
    document.addEventListener('focusout', commit);
    return () => {
      document.removeEventListener('focusout', commit);
      commit();
    };
  }, [commit, nodeId]);

  const draft = draftRef.current && draftRef.current.nodeId === nodeId ? draftRef.current.cfg : null;
  const cfg = draft ?? asObj(node?.data[slot]);

  const patch = (p: Cfg) => {
    const base = draftRef.current && draftRef.current.nodeId === nodeId ? draftRef.current.cfg : asObj(getNode(nodeId)?.data[slot]);
    if (!getNode(nodeId)) return;
    const merged: Cfg = { ...base, ...p };
    for (const k of Object.keys(p)) if (p[k] === undefined) delete merged[k];
    draftRef.current = { nodeId, cfg: merged };
    rerender((n) => n + 1);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(commit, COMMIT_DELAY_MS);
  };

  const kind = node ? nodeKind(node) : 'unknown';
  const issues = node ? validateNode(node, edges) : [];
  const error = (field: string) => issues.find((i) => i.field === field)?.message;
  const Err = ({ field }: { field: string }) => {
    const m = error(field);
    return m ? (
      <p role="alert" className="mt-1 text-meta text-destructive" data-testid={`flow-error-${kind}-${field}`}>
        {m}
      </p>
    ) : null;
  };
  const shell: FormShell = { kind, error, Err };
  return { node, edges, cfg, patch, kind, shell, activeFlow };
}

export const tid = (kind: string, field: string) => `flow-field-${kind}-${field}`;

export function Section({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <div className="space-y-3">
      <Label weight="semibold" className="mb-2 block" data-testid="flow-config-title">
        {title}
      </Label>
      {hint ? <div className="text-xs text-muted-foreground p-2 bg-muted/30 rounded-md break-words" data-testid="flow-config-hint">{hint}</div> : null}
      {children}
    </div>
  );
}

/**
 * A multi-line text field with an "Insert data" picker that inserts the chosen reference text at the cursor.
 * `format` turns the reference path into the text to insert (an expression name, or a `{placeholder}`).
 */
export function PickerTextarea({
  id, testId, pickerTestId, nodeId, label, value, onChange, format, placeholder, className, mono,
}: {
  id: string;
  testId: string;
  pickerTestId: string;
  nodeId: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  format: (ref: string) => string;
  placeholder?: string;
  className?: string;
  mono?: boolean;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const insert = (reference: string) => {
    const text = format(reference);
    const el = ref.current;
    const at = el?.selectionStart ?? value.length;
    const end = el?.selectionEnd ?? at;
    onChange(`${value.slice(0, at)}${text}${value.slice(end)}`);
    requestAnimationFrame(() => {
      el?.focus();
      el?.setSelectionRange(at + text.length, at + text.length);
    });
  };
  return (
    <div>
      <div className="flex justify-between items-center mb-1 min-h-7">
        <Label htmlFor={id} size="sm">{label}</Label>
        <VariablePicker currentNodeId={nodeId} testId={pickerTestId} label={`Insert data into ${label}`} onSelect={(r) => insert(r)} />
      </div>
      <Textarea
        id={id}
        ref={ref}
        data-testid={testId}
        className={`${className ?? 'min-h-[80px]'} w-full${mono ? ' font-mono' : ''}`}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
      />
    </div>
  );
}

export function BranchRows({ nodeId, cfgType, cfg }: { nodeId: string; cfgType: string; cfg: Cfg }) {
  const { activeFlow, setSelectedNode } = useFlowContext();
  const handles = branchHandlesFor(cfgType, cfg);
  if (handles.length === 0) return null;
  return (
    <div className="space-y-1.5" data-testid="flow-branches">
      <Label size="sm">Where each path goes</Label>
      <p className="text-meta text-muted-foreground">Drag from the matching dot on the step, or use its Add step button.</p>
      {handles.map((h) => {
        const edge = activeFlow?.edges.find((e) => e.source === nodeId && edgeRoute(e) === h.route);
        const target = activeFlow?.nodes.find((n) => n.id === edge?.target);
        return (
          <div key={h.route} className="flex items-center justify-between rounded-md border border-border px-2 py-1.5 text-xs" data-testid={`flow-branch-${h.route}`}>
            <span className="font-medium">{h.label}</span>
            {target ? (
              <button type="button" className="text-primary hover:underline truncate max-w-[150px]" onClick={() => setSelectedNode(target.id)}>
                {target.data.label}
              </button>
            ) : (
              <span className="text-muted-foreground" data-testid={`flow-branch-${h.route}-empty`}>Not connected</span>
            )}
          </div>
        );
      })}
    </div>
  );
}

/** What every per-step form receives from the config panel. */
export interface ActionFormProps {
  nodeId: string;
  cfg: Cfg;
  patch: (p: Cfg) => void;
  /** Test id of a field of this step kind. */
  f: (field: string) => string;
  /** Required-field message under a control. */
  Err: (props: { field: string }) => ReactNode;
  title: string;
}
