import { type ReactNode, useCallback, useEffect, useRef, useState } from 'react';
import { Label } from '../../ui/label';
import { fieldKey, isFieldRevealed, setStepHint, touchField, useFrame } from '../frame/frameStore';
import { Textarea } from '../../ui/textarea';
import { VariablePicker } from '../../ui/VariablePicker';
import { branchHandlesFor } from '@/lib/flow/flowBranches';
import { edgeRoute } from '../../../services/flowSerializer';
import { nodeKind, validateNode } from '@/lib/flow-graph/flowValidation';
import { type FlowNodeData } from '../../../types/flow.types';
import { useFlowContext } from '../../../contexts/FlowContext';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';

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
  const { canManage } = useFlowPermissions();
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
  // Required-field messages are for the people who can fix them; a viewer reads the step as it is.
  const issues = node && canManage ? validateNode(node, edges) : [];
  const error = (field: string) => issues.find((i) => i.field === field)?.message;
  // One stable component for the life of the form, reading the latest values through a ref: a new component type on
  // every render would remount the message (and drop its focus listener) on each keystroke.
  const latest = useRef({ nodeId, kind, error });
  latest.current = { nodeId, kind, error };
  const ErrRef = useRef(function Err({ field }: { field: string }) {
    const { nodeId: id, kind: k, error: e } = latest.current;
    return <FieldError nodeId={id} kind={k} field={field} message={e(field)} />;
  });
  const Err = ErrRef.current;
  const shell: FormShell = { kind, error, Err };
  return { node, edges, cfg, patch, kind, shell, activeFlow };
}

/**
 * The message under a required field. It stays hidden on a form nobody has touched: it appears once the person has
 * been in the field and left it, or after a save / publish / run attempt, or when "N things to finish" is used.
 * The (empty) anchor also watches focus leaving the control just above it.
 */
export function FieldError({ nodeId, kind, field, message }: { nodeId: string; kind: string; field: string; message?: string }) {
  const anchor = useRef<HTMLSpanElement>(null);
  const shown = useFrame((s) => isFieldRevealed(s, nodeId, field));
  useEffect(() => {
    // Paths between steps are not a typed field: they are shown by the checklist and the branch rows, not on blur.
    if (field.startsWith('branch.')) return;
    let control: Element | null = anchor.current?.previousElementSibling ?? null;
    while (control && (control as HTMLElement).dataset?.errAnchor !== undefined) control = control.previousElementSibling;
    const target = control ?? anchor.current?.parentElement;
    if (!target) return;
    const onOut = (ev: Event) => {
      const next = (ev as FocusEvent).relatedTarget as Node | null;
      if (!next || !target.contains(next)) touchField(nodeId, field);
    };
    target.addEventListener('focusout', onOut);
    return () => target.removeEventListener('focusout', onOut);
  }, [nodeId, field]);
  return (
    <>
      <span ref={anchor} hidden aria-hidden data-err-anchor={fieldKey(nodeId, field)} />
      {message && shown ? (
        <p role="alert" className="mt-1 text-meta text-destructive" data-testid={`flow-error-${kind}-${field}`}>
          {message}
        </p>
      ) : null}
    </>
  );
}

export const tid = (kind: string, field: string) => `flow-field-${kind}-${field}`;

/**
 * The body of a step's Setup tab. The step's title and kind live in the panel header, so this renders no heading;
 * the longer explanation of the step goes behind the (i) in the header.
 */
export function Section({ hint, children }: { title?: string; hint?: string; children: ReactNode }) {
  useEffect(() => {
    setStepHint(hint ?? null);
    return () => setStepHint(null);
  }, [hint]);
  return <div className="space-y-4">{children}</div>;
}

/**
 * A multi-line text field with an "Use data" picker that inserts the chosen reference text at the cursor.
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
        <VariablePicker currentNodeId={nodeId} testId={pickerTestId} label={`Use data into ${label}`} onSelect={(r) => insert(r)} />
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
