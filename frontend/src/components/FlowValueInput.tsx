import { useRef, useState } from 'react';
import { VariablePicker } from './ui/VariablePicker';
import { useFlowContext } from '../contexts/FlowContext';
import { Input } from './ui/input';
import { Textarea } from './ui/textarea';
import { Label } from './ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import {
  insertReferenceIntoValue,
  isInvalidValueJson,
  templateVarsToText,
  textToValue,
  valueMode,
  valueToText,
  type ValueMode,
} from '@/lib/flow-graph/flowValue';

interface FlowValueInputProps {
  id: string;
  label: string;
  value: unknown;
  onChange: (value: unknown) => void;
  optional?: boolean;
  /** data-testid for the value control; the mode select gets `${testId}-mode`. */
  testId?: string;
  /** Step this field belongs to. When set, an "Insert data" picker lists the trigger and earlier steps. */
  nodeId?: string;
  /** Example shown in an empty literal value. */
  placeholder?: string;
  /** One line under the value: where to find it. */
  hint?: string;
}

const MODE_LABELS: Record<ValueMode, string> = {
  literal: 'Literal',
  reference: 'Reference ($from)',
  template: 'Template',
  json: 'JSON',
};

/** One line under a value that is not plain text: what that way of giving a value means. */
const MODE_HELP: Record<ValueMode, string> = {
  literal: 'Typed exactly as written.',
  reference: 'Takes the value from the trigger or an earlier step, for example input.name. Use Insert data to pick it.',
  template: 'Text with {name} placeholders. Each placeholder is filled with data from the trigger or an earlier step.',
  json: 'A list or an object, for example ["a", "b"] or {"name": "Ada"}.',
};

/**
 * Edits one graph-IR Value: a literal, a `$from` reference (e.g. `input.sender_id`,
 * `node_a.value`), a `$template` with `vars`, or a JSON array/object.
 */
export function FlowValueInput({ id, label, value, onChange, optional, testId, nodeId, placeholder, hint }: FlowValueInputProps) {
  // The mode lives in the value for references, templates and JSON objects/arrays. A value that is still
  // plain text (empty, or JSON that does not parse yet) would fall back to "Literal", so remember the pick.
  const [picked, setPicked] = useState<ValueMode | null>(null);
  const derived = valueMode(value);
  const mode: ValueMode = derived !== 'literal' ? derived : picked ?? 'literal';
  const text = valueToText(value);
  const varsText = templateVarsToText(value);
  const { activeFlow } = useFlowContext();
  const areaRef = useRef<HTMLTextAreaElement>(null);
  /** A reference path in words: the step's name for a step id. */
  const sourceName = (path: string) => {
    const root = path.split(/[.[]/)[0];
    if (root === 'input') return 'the trigger input';
    if (root === 'trigger') return 'the trigger details';
    const step = activeFlow?.nodes.find((n) => n.id === root);
    return step ? `the result of "${step.data.label}"` : path;
  };
  // Bumped when the picker rewrites the template variables so their editor shows the new text.
  const [varsVersion, setVarsVersion] = useState(0);

  const insertRef = (ref: string, name: string) => {
    const caret = mode === 'json' ? areaRef.current?.selectionStart ?? undefined : undefined;
    const next = insertReferenceIntoValue(value, mode, ref, name, caret);
    setPicked(next.mode);
    if (next.mode === 'template') setVarsVersion((v) => v + 1);
    onChange(next.value);
    requestAnimationFrame(() => {
      const el = document.getElementById(id) as HTMLInputElement | HTMLTextAreaElement | null;
      el?.focus();
      if (el && mode !== 'json') el.setSelectionRange(el.value.length, el.value.length);
    });
  };

  const singleLine = mode === 'literal' || mode === 'reference';
  const modeSelect = (
    <Select
      value={mode}
      onValueChange={(m) => {
        setPicked(m as ValueMode);
        onChange(textToValue(m as ValueMode, text, varsText));
      }}
    >
      <SelectTrigger
        id={`${id}-mode`}
        data-testid={testId ? `${testId}-mode` : undefined}
        aria-label={`${label}: how the value is given`}
        size="sm"
        className="w-[170px]"
      >
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {(Object.keys(MODE_LABELS) as ValueMode[]).map((m) => (
          <SelectItem key={m} value={m}>
            {MODE_LABELS[m]}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between gap-2 min-h-7">
        <Label htmlFor={id} size="sm" className="min-w-0 truncate">
          {label}
          {optional ? ' (optional)' : ''}
        </Label>
        {nodeId ? (
          <VariablePicker
            currentNodeId={nodeId}
            testId={testId ? `${testId}-picker` : undefined}
            label={`Insert data into ${label}`}
            onSelect={insertRef}
          />
        ) : null}
      </div>
      {singleLine ? (
        <div className="space-y-1.5">
          {modeSelect}
          <Input
            id={id}
            data-testid={testId}
            value={text}
            className={mode === 'reference' ? 'w-full min-w-0 font-mono text-xs' : 'w-full min-w-0'}
            placeholder={mode === 'reference' ? 'e.g., input.sender_id' : placeholder}
            onChange={(e) => onChange(textToValue(mode, e.target.value))}
          />
        </div>
      ) : (
        <>
          {modeSelect}
          <Textarea
            id={id}
            ref={areaRef}
            data-testid={testId}
            className="min-h-[60px] w-full font-mono"
            value={text}
            placeholder={mode === 'template' ? 'Refund for #{order}' : '[]'}
            onChange={(e) => onChange(textToValue(mode, e.target.value, varsText))}
          />
        </>
      )}
      {hint && (
        <p className="text-[11px] leading-snug text-muted-foreground break-words" data-testid={testId ? `${testId}-hint` : undefined}>{hint}</p>
      )}
      {mode !== 'literal' && (
        <p className="text-[11px] leading-snug text-muted-foreground break-words" data-testid={testId ? `${testId}-mode-help` : undefined}>{MODE_HELP[mode]}</p>
      )}
      {mode === 'json' && isInvalidValueJson(text) && (
        <p className="text-[10px] text-destructive">Not valid JSON — saved as plain text.</p>
      )}
      {mode === 'template' && (
        <>
          {Object.keys((value as { vars?: Record<string, unknown> }).vars ?? {}).length > 0 && (
            <ul className="space-y-0.5 text-[11px] text-muted-foreground" data-testid={testId ? `${testId}-vars-summary` : undefined}>
              {Object.entries((value as { vars?: Record<string, { $from?: string }> }).vars ?? {}).map(([name, v]) => (
                <li key={name} className="truncate">
                  <span className="font-mono">{`{${name}}`}</span> is filled with{' '}
                  <span title={typeof v?.$from === 'string' ? v.$from : undefined}>{typeof v?.$from === 'string' ? sourceName(v.$from) : 'a value'}</span>
                </li>
              ))}
            </ul>
          )}
          <details className="text-[11px]">
            <summary className="cursor-pointer text-muted-foreground">Edit the values (advanced)</summary>
            <Label htmlFor={`${id}-vars`} size="sm" className="mt-1 block">
              Which data fills each {'{name}'}, as JSON
            </Label>
            <Textarea
              id={`${id}-vars`}
              className="min-h-[50px] w-full font-mono"
              defaultValue={varsText}
              key={`${id}-${mode}-${varsVersion}`}
              onChange={(e) => onChange(textToValue('template', text, e.target.value))}
            />
            {isInvalidValueJson(varsText) && (
              <p className="text-[10px] text-destructive">That is not valid JSON.</p>
            )}
          </details>
        </>
      )}
    </div>
  );
}
