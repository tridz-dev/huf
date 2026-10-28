import { Input } from './ui/input';
import { Textarea } from './ui/textarea';
import { Label } from './ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import {
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
export function FlowValueInput({ id, label, value, onChange, optional, testId }: FlowValueInputProps) {
  const mode = valueMode(value);
  const text = valueToText(value);
  const varsText = templateVarsToText(value);

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between gap-2">
        <Label htmlFor={id} size="sm">
          {label}
          {optional ? ' (optional)' : ''}
        </Label>
        <Select
          value={mode}
          onValueChange={(m) => onChange(textToValue(m as ValueMode, text, varsText))}
        >
          <SelectTrigger id={`${id}-mode`} data-testid={testId ? `${testId}-mode` : undefined} size="sm" className="w-[150px]">
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
      </div>
      {mode === 'literal' || mode === 'reference' ? (
        <Input
          id={id}
          data-testid={testId}
          value={text}
          className={mode === 'reference' ? 'font-mono text-xs' : undefined}
          placeholder={mode === 'reference' ? 'e.g., input.sender_id' : undefined}
          onChange={(e) => onChange(textToValue(mode, e.target.value))}
        />
      ) : (
        <Textarea
          id={id}
          data-testid={testId}
          className="min-h-[60px] w-full font-mono"
          value={text}
          placeholder={mode === 'template' ? 'Refund for #{order}' : '[]'}
          onChange={(e) => onChange(textToValue(mode, e.target.value, varsText))}
        />
      )}
      {mode === 'json' && isInvalidValueJson(text) && (
        <p className="text-[10px] text-destructive">Not valid JSON — saved as plain text.</p>
      )}
      {mode === 'template' && (
        <>
          <Label htmlFor={`${id}-vars`} size="sm">
            Template vars (JSON, e.g. {'{"order": {"$from": "input.order"}}'})
          </Label>
          <Textarea
            id={`${id}-vars`}
            className="min-h-[50px] w-full font-mono"
            defaultValue={varsText}
            key={`${id}-${mode}`}
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
