import { useRef, useState } from 'react';
import { VariablePicker } from './ui/VariablePicker';
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
} from '@/lib/flowValue';

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
}

const MODE_LABELS: Record<ValueMode, string> = {
  literal: 'Literal',
  reference: 'Reference ($from)',
  template: 'Template',
  json: 'JSON',
};

/**
 * Edits one graph-IR Value: a literal, a `$from` reference (e.g. `input.sender_id`,
 * `node_a.value`), a `$template` with `vars`, or a JSON array/object.
 */
export function FlowValueInput({ id, label, value, onChange, optional, testId, nodeId }: FlowValueInputProps) {
  // The mode lives in the value for references, templates and JSON objects/arrays. A value that is still
  // plain text (empty, or JSON that does not parse yet) would fall back to "Literal", so remember the pick.
  const [picked, setPicked] = useState<ValueMode | null>(null);
  const derived = valueMode(value);
  const mode: ValueMode = derived !== 'literal' ? derived : picked ?? 'literal';
  const text = valueToText(value);
  const varsText = templateVarsToText(value);
  const areaRef = useRef<HTMLTextAreaElement>(null);
  // Bumped when the picker rewrites the template variables so their editor shows the new text.
  const [varsVersion, setVarsVersion] = useState(0);

  const insertRef = (ref: string, name: string) => {
    const caret = mode === 'json' ? areaRef.current?.selectionStart ?? undefined : undefined;
    const next = insertReferenceIntoValue(value, mode, ref, name, caret);
    setPicked(next.mode);
    if (next.mode === 'template') setVarsVersion((v) => v + 1);
    onChange(next.value);
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
        className={singleLine ? 'w-[118px] shrink-0' : 'w-[170px]'}
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
        <div className="flex items-center gap-1.5">
          {modeSelect}
          <Input
            id={id}
            data-testid={testId}
            value={text}
            className={mode === 'reference' ? 'min-w-0 font-mono text-xs' : 'min-w-0'}
            placeholder={mode === 'reference' ? 'e.g., input.sender_id' : undefined}
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
      {mode === 'json' && isInvalidValueJson(text) && (
        <p className="text-[10px] text-destructive">Not valid JSON — saved as plain text.</p>
      )}
      {mode === 'template' && (
        <>
          <Label htmlFor={`${id}-vars`} size="sm">
            Values used in the template (JSON, e.g. {'{"order": {"$from": "input.order"}}'})
          </Label>
          <Textarea
            id={`${id}-vars`}
            className="min-h-[50px] w-full font-mono"
            defaultValue={varsText}
            key={`${id}-${mode}-${varsVersion}`}
            onChange={(e) => onChange(textToValue('template', text, e.target.value))}
          />
          {isInvalidValueJson(varsText) && (
            <p className="text-[10px] text-destructive">Vars are not valid JSON.</p>
          )}
        </>
      )}
    </div>
  );
}
