import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { fromTextRefs, toTextRefs } from '@/lib/flow-data/textRefs';
import { getAppNodeType } from '@/lib/flow-graph/appNodeTypes';
import type { SchemaProp } from '@/services/flow/nodeTypesApi';
import { Input } from '../../ui/input';
import { Label } from '../../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../ui/select';
import { DataInput } from '../data/DataInput';
import { DoctypePicker } from '../DoctypePicker';
import { FieldHint } from '../FieldHint';
import { ValueField } from './fields';
import { type ActionFormProps, type Cfg, asObj, Section } from './formKit';
import { useDoctypeOptions } from './data/DocGetForm';
import { useAsValue } from './useAsValue';

type RowProps = {
  name: string;
  prop: SchemaProp;
  value: unknown;
  onChange: (v: unknown) => void;
  nodeId: string;
  f: ActionFormProps['f'];
  Err: ActionFormProps['Err'];
  /** Field key for the test id and the required-field message (dotted inside a group). */
  path: string;
  disabled: boolean;
};

function TemplateRow({ prop, value, onChange, nodeId, f, path, disabled, Err }: RowProps) {
  const stored = typeof value === 'string' ? value : '';
  const [shown, toStored] = useAsValue(stored, toTextRefs, (v) => fromTextRefs(v) ?? '');
  return <ValueField field={path} f={f} Err={Err} nodeId={nodeId} label={prop.title} hint={prop.description} disabled={disabled} value={shown} onChange={(v) => onChange(toStored(v))} />;
}

function DoctypeRow({ prop, value, onChange, f, path, disabled, Err }: RowProps) {
  const { options, loading } = useDoctypeOptions();
  const id = `schema-${path.replace(/[^a-z0-9]+/gi, '-')}`;
  return (
    <div>
      <Label htmlFor={id} size="sm">{prop.title}</Label>
      <DoctypePicker id={id} testId={f(path)} options={options} loading={loading} disabled={disabled} value={typeof value === 'string' ? value : ''} onChange={onChange} />
      {prop.description && <FieldHint>{prop.description}</FieldHint>}
      <Err field={path} />
    </div>
  );
}

function SchemaRow(props: RowProps) {
  const { name, prop, value, onChange, nodeId, f, Err, path, disabled } = props;
  const label = prop.title ?? name;
  const id = `schema-${path.replace(/[^a-z0-9]+/gi, '-')}`;
  const widget = prop['x-huf-widget'];
  const hint = prop.description ? <FieldHint>{prop.description}</FieldHint> : null;

  if (widget === 'data-ref') return <ValueField field={path} f={f} Err={Err} nodeId={nodeId} label={label} hint={prop.description} disabled={disabled} value={value} onChange={onChange} />;
  if (widget === 'template') return <TemplateRow {...props} prop={{ ...prop, title: label }} />;
  if (widget === 'doctype') return <DoctypeRow {...props} prop={{ ...prop, title: label }} />;

  if (prop.type === 'object') {
    const inner = asObj(value);
    return (
      <fieldset className="space-y-3 rounded-md border p-3" data-testid={f(path)}>
        <legend className="px-1 text-xs font-medium">{label}</legend>
        {hint}
        {Object.entries(prop.properties ?? {}).map(([k, p]) => (
          <SchemaRow key={k} {...props} name={k} prop={p} path={`${path}.${k}`} value={inner[k]} onChange={(v) => onChange(setKey(inner, k, v))} />
        ))}
      </fieldset>
    );
  }
  if (prop.type === 'boolean') {
    return (
      <div>
        <label htmlFor={id} className="flex items-center gap-2 text-sm">
          <input id={id} type="checkbox" data-testid={f(path)} disabled={disabled} checked={value === true} onChange={(e) => onChange(e.target.checked)} />
          {label}
        </label>
        {hint}
        <Err field={path} />
      </div>
    );
  }
  if (prop.enum) {
    return (
      <div>
        <Label htmlFor={id} size="sm">{label}</Label>
        <Select value={typeof value === 'string' ? value : ''} disabled={disabled} onValueChange={onChange}>
          <SelectTrigger id={id} data-testid={f(path)}><SelectValue placeholder="Choose" /></SelectTrigger>
          <SelectContent>{prop.enum.map((o) => <SelectItem key={o} value={o}>{o}</SelectItem>)}</SelectContent>
        </Select>
        {hint}
        <Err field={path} />
      </div>
    );
  }
  if (prop.type === 'number' || prop.type === 'integer') {
    return (
      <div>
        <Label htmlFor={id} size="sm">{label}</Label>
        <Input id={id} data-testid={f(path)} type="number" disabled={disabled} value={typeof value === 'number' ? String(value) : ''}
          onChange={(e) => onChange(e.target.value.trim() === '' ? undefined : Number(e.target.value))} />
        {hint}
        <Err field={path} />
      </div>
    );
  }
  if (prop.type === 'array') {
    const list = Array.isArray(value) ? (value as string[]) : [];
    return (
      <div>
        <Label htmlFor={id} size="sm">{label}</Label>
        <Input id={id} data-testid={f(path)} disabled={disabled} placeholder="Separate with commas" defaultValue={list.join(', ')}
          onChange={(e) => { const items = e.target.value.split(',').map((s) => s.trim()).filter(Boolean); onChange(items.length ? items : undefined); }} />
        {hint}
        <Err field={path} />
      </div>
    );
  }
  return (
    <div>
      <Label htmlFor={id} size="sm">{label}</Label>
      <Input id={id} data-testid={f(path)} disabled={disabled} value={typeof value === 'string' ? value : ''} onChange={(e) => onChange(e.target.value === '' ? undefined : e.target.value)} />
      {hint}
      <Err field={path} />
    </div>
  );
}

const setKey = (obj: Cfg, key: string, v: unknown): Cfg => {
  const next = { ...obj, [key]: v };
  if (v === undefined) delete next[key];
  return next;
};

/** The settings of a step an installed app added, drawn from the app's JSON Schema. */
export function SchemaNodeForm({ nodeId, cfg, patch, f, Err, title }: ActionFormProps) {
  const { canManage } = useFlowPermissions();
  const def = getAppNodeType(cfg.backend_type);
  if (!def) {
    return (
      <div role="alert" className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-xs text-destructive" data-testid="flow-schema-missing">
        This step comes from an app that is not installed on this site. Remove the step or install the app.
      </div>
    );
  }
  const entries = Object.entries(def.config_schema?.properties ?? {});
  return (
    <Section title={title} hint={def.description}>
      <FieldHint testId="flow-schema-app">Added by {def.app}</FieldHint>
      {entries.length === 0 && <p className="text-xs text-muted-foreground" data-testid="flow-schema-empty">This step has no settings.</p>}
      {entries.map(([name, prop]) => (
        <SchemaRow key={name} name={name} prop={prop} path={name} value={cfg[name]} onChange={(v) => patch({ [name]: v })} nodeId={nodeId} f={f} Err={Err} disabled={!canManage} />
      ))}
    </Section>
  );
}
export { DataInput };
