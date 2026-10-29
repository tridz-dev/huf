import { useRef, type ReactNode } from 'react';
import { Input } from '../ui/input';
import { Textarea } from '../ui/textarea';
import { Button } from '../ui/button';
import { Label } from '../ui/label';
import { Badge } from '../ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { FlowValueInput } from '../FlowValueInput';
import {
  CODE_NO_PERMISSION_NOTE,
  DEFAULT_CODE_TIMEOUT_S,
  MAX_CODE_BYTES,
  byteLength,
  profileLabel,
  usableProfiles,
} from '@/lib/flow-graph/codeFlow';
import { useCodeFlowStatus } from '@/lib/flow-graph/useCodeFlowStatus';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import type { CodeFlowProfile } from '@/services/flow/codeFlowApi';

type Cfg = Record<string, unknown>;

const asObj = (v: unknown): Cfg => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Cfg) : {});
const str = (v: unknown): string => (typeof v === 'string' ? v : '');

/** A Python editor: a monospace textarea with a line-number gutter that scrolls with it. */
function CodeEditor({ value, onChange, disabled }: { value: string; onChange: (v: string) => void; disabled?: boolean }) {
  const gutterRef = useRef<HTMLPreElement>(null);
  const lines = Math.max(value.split('\n').length, 8);
  const numbers = Array.from({ length: lines }, (_, i) => i + 1).join('\n');
  return (
    <div className="flex rounded-md border border-input bg-background overflow-hidden focus-within:ring-2 focus-within:ring-ring">
      <pre
        ref={gutterRef}
        aria-hidden
        className="select-none overflow-hidden bg-muted/40 px-2 py-2 text-right font-mono text-micro leading-5 text-muted-foreground"
        data-testid="flow-code-gutter"
      >
        {numbers}
      </pre>
      <Textarea
        id="code-run-code"
        data-testid="flow-code-editor"
        aria-label="Python code"
        className="min-h-[168px] max-h-[360px] min-w-0 resize-y rounded-none border-0 bg-transparent px-2 py-2 font-mono text-micro leading-5 whitespace-pre overflow-x-auto focus-visible:ring-0"
        wrap="off"
        spellCheck={false}
        autoCapitalize="off"
        autoCorrect="off"
        value={value}
        disabled={disabled}
        placeholder={"print('Hello')\nresult = 1 + 1"}
        onChange={(e) => onChange(e.target.value)}
        onScroll={(e) => {
          if (gutterRef.current) gutterRef.current.scrollTop = e.currentTarget.scrollTop;
        }}
      />
    </div>
  );
}

function Help() {
  return (
    <details className="rounded-md bg-muted/30 p-2 text-xs text-muted-foreground" data-testid="flow-code-help">
      <summary className="cursor-pointer font-medium text-foreground">How your code runs</summary>
      <ul className="mt-2 list-disc space-y-1 pl-4">
        <li>It is Python, run in a sandbox. Imports are not available unless the profile allows them.</li>
        <li><code>print()</code> output is saved as the step&apos;s <em>stdout</em>.</li>
        <li><code>inputs</code> is a dictionary of the values you map below, for example <code>inputs[&apos;name&apos;]</code>. It holds data only.</li>
        <li>Set a variable called <code>result</code> to hand a value (anything that fits in JSON) to the next steps.</li>
        <li>Scratch profiles let you <code>open(&apos;notes.txt&apos;, &apos;w&apos;)</code> and read files in a private folder with no subfolders. It is deleted when the step ends.</li>
        <li>There is no network access. The step stops at the time limit.</li>
      </ul>
    </details>
  );
}

interface CodeRunFieldsProps {
  nodeId: string;
  cfg: Cfg;
  patch: (p: Cfg) => void;
  Err: (props: { field: string }) => ReactNode;
}

/** The body of the Execute code step form (rendered inside the sidebar's Section). */
export function CodeRunFields({ nodeId, cfg, patch, Err }: CodeRunFieldsProps) {
  const { status, loading } = useCodeFlowStatus();
  const { canExecuteCode } = useFlowPermissions();
  // Without permission (or while the server says code is off) the step can be read but not changed.
  const noPermission = !loading && (!status?.available || !canExecuteCode);
  const code = str(cfg.code);
  const profileName = str(cfg.profile);
  const profiles = usableProfiles(status);
  const current: CodeFlowProfile | undefined = (status?.profiles ?? []).find((p) => p.name === profileName);
  const options = profiles.some((p) => p.name === profileName) || !profileName
    ? profiles
    : [...profiles, ...(current ? [current] : [{ name: profileName, approval_mode: 'Auto Approve' as const, max_wall_time_s: 0, usable: false }])];
  const maxTimeout = current?.max_wall_time_s || 0;
  const timeout = typeof cfg.timeout_s === 'number' ? cfg.timeout_s : '';
  const inputs = asObj(cfg.inputs);
  const entries = Object.entries(inputs);
  const size = byteLength(code);
  const needsApproval = Boolean(current && current.approval_mode !== 'Auto Approve');

  const clampTimeout = (n: number, max: number) => Math.max(1, max > 0 ? Math.min(n, max) : n);

  return (
    <fieldset disabled={noPermission} className="contents">
      {noPermission && (
        <p role="status" className="rounded-md bg-muted px-2 py-1.5 text-xs text-muted-foreground" data-testid="flow-code-readonly-note">
          {CODE_NO_PERMISSION_NOTE}
        </p>
      )}
      <div>
        <Label htmlFor="code-run-code" size="sm" className="mb-1 block">Python code</Label>
        <CodeEditor value={code} onChange={(v) => patch({ code: v })} disabled={noPermission} />
        {size > MAX_CODE_BYTES * 0.8 && (
          <p className="mt-1 text-micro text-muted-foreground">{Math.round(size / 1024)} KB of 64 KB used</p>
        )}
        <Err field="code" />
      </div>
      <Help />
      <div>
        <Label htmlFor="code-run-profile" size="sm">How it may run</Label>
        <Select
          value={profileName || undefined}
          onValueChange={(v) => {
            const next = (status?.profiles ?? []).find((p) => p.name === v);
            const patchTimeout = typeof cfg.timeout_s === 'number' && next?.max_wall_time_s ? { timeout_s: clampTimeout(cfg.timeout_s, next.max_wall_time_s) } : {};
            patch({ profile: v, ...patchTimeout });
          }}
        >
          <SelectTrigger id="code-run-profile" data-testid="flow-code-profile">
            <SelectValue placeholder="Choose a profile..." />
          </SelectTrigger>
          <SelectContent>
            {options.map((p) => (
              <SelectItem key={p.name} value={p.name} disabled={!p.usable} data-testid={`flow-option-code-profile-${p.name}`}>
                {p.usable ? profileLabel(p) : `${p.name} - not available`}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {needsApproval && (
          <div className="mt-1.5 space-y-1">
            <Badge variant="pill-warning" data-testid="flow-code-profile-badge">Needs approval each run</Badge>
            <p className="text-micro text-muted-foreground">The flow waits until an administrator approves each run in the approvals bell.</p>
          </div>
        )}
        <Err field="profile" />
      </div>
      <div>
        <Label htmlFor="code-run-timeout" size="sm">Time limit (seconds)</Label>
        <Input
          id="code-run-timeout"
          data-testid="flow-code-timeout"
          type="number"
          min={1}
          max={maxTimeout || undefined}
          value={timeout}
          placeholder={String(status?.default_timeout_s ?? DEFAULT_CODE_TIMEOUT_S)}
          onChange={(e) => {
            if (e.target.value === '') return patch({ timeout_s: undefined });
            const n = parseInt(e.target.value, 10);
            if (Number.isNaN(n)) return;
            patch({ timeout_s: clampTimeout(n, maxTimeout) });
          }}
        />
        {maxTimeout > 0 && <p className="mt-1 text-micro text-muted-foreground">Up to {maxTimeout} seconds for this profile.</p>}
        <Err field="timeout_s" />
      </div>
      <div className="space-y-2">
        <Label size="sm">Inputs for your code</Label>
        {entries.length === 0 && (
          <p className="text-xs text-muted-foreground">No inputs yet. Add one to use data from the trigger or an earlier step as <code>inputs[&apos;name&apos;]</code>.</p>
        )}
        {entries.map(([name, val], i) => (
          <div key={i} className="space-y-2 rounded-md border bg-muted/20 p-3">
            <div className="flex items-end gap-2">
              <div className="flex-1">
                <Label htmlFor={`code-input-${i}-name`} size="sm">Name</Label>
                <Input
                  id={`code-input-${i}-name`}
                  data-testid={`flow-code-input-key-${i}`}
                  value={name}
                  className="font-mono text-xs"
                  onChange={(e) => {
                    const next = e.target.value;
                    if (next !== name && next in inputs) return; // never merge two inputs into one
                    patch({ inputs: Object.fromEntries(entries.map(([k, v], j) => (j === i ? [next, v] : [k, v]))) });
                  }}
                />
              </div>
              <Button
                variant="ghost"
                size="sm"
                aria-label="Remove input"
                data-testid={`flow-code-input-remove-${i}`}
                className="px-2 text-destructive"
                onClick={() => patch({ inputs: Object.fromEntries(entries.filter((_, j) => j !== i)) })}
              >
                ×
              </Button>
            </div>
            <FlowValueInput
              id={`code-input-${i}-value`}
              nodeId={nodeId}
              testId={`flow-code-input-value-${i}`}
              label="Value"
              value={val}
              onChange={(v) => patch({ inputs: Object.fromEntries(entries.map(([k, o], j) => (j === i ? [k, v] : [k, o]))) })}
            />
          </div>
        ))}
        <Button
          variant="outline"
          size="sm"
          className="w-full"
          data-testid="flow-code-inputs-add"
          onClick={() => {
            let n = entries.length + 1;
            while (`input_${n}` in inputs) n += 1;
            patch({ inputs: { ...inputs, [`input_${n}`]: '' } });
          }}
        >
          Add input
        </Button>
        <Err field="inputs" />
      </div>
    </fieldset>
  );
}

