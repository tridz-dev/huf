import { Checkbox } from '../../ui/checkbox';
import { Input } from '../../ui/input';
import { Label } from '../../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../ui/select';
import { Switch } from '../../ui/switch';
import { Textarea } from '../../ui/textarea';
import { FieldHint } from '../FieldHint';
import { WordListEditor } from './WordListEditor';
import type { GatewayParamSpec, GatewayParamValue } from '@/lib/flow-gateway/gatewayTrigger.types';

const words = (v: GatewayParamValue): string[] => (Array.isArray(v) ? v : typeof v === 'string' && v ? [v] : []);

interface Props {
  spec: GatewayParamSpec;
  value: GatewayParamValue;
  onChange: (value: GatewayParamValue) => void;
  /** Message under the control (a problem to fix), already worded for a person. */
  error?: string;
  disabled?: boolean;
}

const PLACEHOLDER: Partial<Record<GatewayParamSpec['type'], string>> = { people: 'A name or number, then Enter', tags: 'Type a word, then Enter' };

/**
 * One option of a chat trigger, drawn from its registry description. The control follows `type`; a new option the
 * server adds needs no code here. Test ids: `flow-param-<key>` for the control, `flow-param-<key>-add` on a word list.
 */
export function GatewayParamField({ spec, value, onChange, error, disabled }: Props) {
  const id = `flow-param-${spec.key}`;
  const label = (
    <Label htmlFor={id} size="sm">{spec.label}</Label>
  );
  const help = spec.help ? <FieldHint testId={`${id}-help`}>{spec.help}</FieldHint> : null;
  const problem = error ? <p role="alert" className="mt-1 text-meta text-destructive" data-testid={`${id}-error`}>{error}</p> : null;

  if (spec.type === 'boolean') {
    return (
      <div data-testid={`${id}-row`}>
        <div className="flex items-start justify-between gap-3">
          <Label htmlFor={id} size="sm" className="leading-snug">{spec.label}</Label>
          <Switch id={id} data-testid={id} checked={value === true} disabled={disabled} onCheckedChange={(on) => onChange(on)} />
        </div>
        {help}
        {problem}
      </div>
    );
  }

  let control;
  switch (spec.type) {
    case 'tags':
    case 'people':
      control = (
        <WordListEditor id={id} testId={id} label={spec.label} words={words(value)} placeholder={PLACEHOLDER[spec.type]} onChange={onChange} />
      );
      break;
    case 'multiselect': {
      const picked = words(value);
      control = (
        <div className="space-y-1.5" data-testid={id} role="group" aria-label={spec.label}>
          {spec.options.map((o) => (
            <Label key={o.value} className="flex items-center gap-2 text-sm font-normal" data-testid={`${id}-option-${o.value}`}>
              <Checkbox
                checked={picked.includes(o.value)}
                disabled={disabled}
                onCheckedChange={(on) => onChange(on ? [...picked, o.value] : picked.filter((p) => p !== o.value))}
              />
              {o.label}
            </Label>
          ))}
        </div>
      );
      break;
    }
    case 'select':
      control = (
        <Select value={typeof value === 'string' && value ? value : undefined} onValueChange={(v) => onChange(v)} disabled={disabled}>
          <SelectTrigger id={id} data-testid={id}>
            <SelectValue placeholder="Choose" />
          </SelectTrigger>
          <SelectContent>
            {spec.options.map((o) => (
              <SelectItem key={o.value} value={o.value} data-testid={`${id}-option-${o.value}`}>{o.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      );
      break;
    case 'number':
      control = (
        <Input
          id={id}
          data-testid={id}
          type="number"
          min={0}
          inputMode="numeric"
          disabled={disabled}
          value={typeof value === 'number' ? value : ''}
          onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))}
        />
      );
      break;
    case 'textarea':
      control = <Textarea id={id} data-testid={id} rows={3} disabled={disabled} value={typeof value === 'string' ? value : ''} onChange={(e) => onChange(e.target.value)} />;
      break;
    default:
      control = <Input id={id} data-testid={id} disabled={disabled} value={typeof value === 'string' ? value : ''} onChange={(e) => onChange(e.target.value)} />;
  }

  return (
    <div data-testid={`${id}-row`}>
      {label}
      <div className="mt-1">{control}</div>
      {help}
      {problem}
    </div>
  );
}
