import { Button } from '../../ui/button';
import { FieldHint } from '../FieldHint';
import { FlowValueInput } from '../../FlowValueInput';
import { Input } from '../../ui/input';
import { Label } from '../../ui/label';
import { type ActionFormProps, asObj, Section, str } from './formKit';

export function DocCreateForm({ nodeId, cfg, patch, f, Err, title }: ActionFormProps) {

  const fields = asObj(cfg.fields);
  const entries = Object.entries(fields);
  return (
    <Section title={title} hint="Creates a new record, for example a ToDo. Only document types your administrator has allowed can be created here. Details of the new record go to the next step.">
      <div>
        <Label htmlFor="doc-create-doctype" size="sm">Document type</Label>
        <Input id="doc-create-doctype" data-testid={f('doctype')} value={str(cfg.doctype)} onChange={(e) => patch({ doctype: e.target.value })} placeholder="ToDo" />
        <FieldHint testId="flow-hint-doc-create-doctype">The kind of record to create, as named in the app (for example ToDo or Customer).</FieldHint>
        <Err field="doctype" />
      </div>
      {entries.map(([name, val], i) => (
        <div key={i} className="p-3 bg-muted/20 border rounded-md space-y-2">
          <div className="flex items-end gap-2">
            <div className="flex-1">
              <Label htmlFor={`doc-field-${i}-name`} size="sm">Field name</Label>
              <Input id={`doc-field-${i}-name`} data-testid={f(`fields.${i}.name`)} placeholder="description" value={name} onChange={(e) => patch({ fields: Object.fromEntries(entries.map(([k, v], j) => (j === i ? [e.target.value, v] : [k, v]))) })} />
            </div>
            <Button variant="ghost" size="sm" aria-label="Remove field" className="px-2 text-destructive" onClick={() => patch({ fields: Object.fromEntries(entries.filter((_, j) => j !== i)) })}>×</Button>
          </div>
          <FlowValueInput id={`doc-field-${i}-value`} nodeId={nodeId} testId={f(`fields.${i}.value`)} label="Value" value={val} onChange={(v) => patch({ fields: Object.fromEntries(entries.map(([k, o], j) => (j === i ? [k, v] : [k, o]))) })} />
        </div>
      ))}
      <Button variant="outline" size="sm" className="w-full" data-testid={f('fields.add')} onClick={() => patch({ fields: { ...fields, [`field_${entries.length + 1}`]: '' } })}>
        Add field
      </Button>
      <FieldHint testId="flow-hint-doc-create-fields">One row per field to fill in. The field name is the one shown in the record's form, in lowercase with underscores.</FieldHint>
    </Section>
  );
}
