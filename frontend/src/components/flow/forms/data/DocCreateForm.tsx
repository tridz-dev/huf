import { useEffect, useMemo, useState } from 'react';
import { X } from 'lucide-react';
import { Button } from '../../../ui/button';
import { Combobox } from '../../../ui/combobox';
import { DataInput } from '../../data/DataInput';
import { FieldHint } from '../../FieldHint';
import { Input } from '../../../ui/input';
import { Label } from '../../../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../ui/select';
import { type CreateDocField, type CreateDocType, listCreateDocFields, listCreateDocTypes } from '@/services/flow/formOptionsApi';
import { type ActionFormProps, asObj, Section, str } from '../formKit';

const KIND_HINT: Record<CreateDocField['kind'], string> = {
  text: '',
  longtext: '',
  number: 'A number, for example 5.',
  yesno: '',
  date: 'A date written as year-month-day, for example 2026-10-29.',
  choice: '',
};

/** The records a flow may create, and for the chosen kind the fields it can fill in: pick them by name, never type a field code. */
export function DocCreateForm({ nodeId, cfg, patch, f, Err, title }: ActionFormProps) {
  const [types, setTypes] = useState<CreateDocType[] | null>(null);
  const [typesFailed, setTypesFailed] = useState(false);
  const [fieldList, setFieldList] = useState<CreateDocField[] | null>(null);
  const doctype = str(cfg.doctype);
  const fields = asObj(cfg.fields);

  useEffect(() => {
    listCreateDocTypes().then((l) => setTypes(l)).catch(() => { setTypes([]); setTypesFailed(true); });
  }, []);
  useEffect(() => {
    setFieldList(null);
    if (!doctype) return;
    let live = true;
    listCreateDocFields(doctype).then((l) => live && setFieldList(l)).catch(() => live && setFieldList([]));
    return () => { live = false; };
  }, [doctype]);

  const byName = useMemo(() => new Map((fieldList ?? []).map((fld) => [fld.fieldname, fld])), [fieldList]);
  const known = types?.find((t) => t.name === doctype);
  const typeOptions = useMemo(() => {
    const list = (types ?? []).map((t) => ({ value: t.name, label: t.label, subtitle: t.label !== t.name ? t.name : undefined }));
    return doctype && !known ? [{ value: doctype, label: doctype, subtitle: 'Not allowed here' }, ...list] : list;
  }, [types, doctype, known]);
  const unlisted = Boolean(doctype && types && types.length > 0 && !known);
  const entries = Object.entries(fields);
  const addable = (fieldList ?? []).filter((fld) => !(fld.fieldname in fields));

  const chooseType = async (next: string) => {
    if (!next || next === doctype) return;
    // A new kind of record starts with the fields it cannot do without.
    let required: Record<string, unknown> = {};
    try {
      required = Object.fromEntries((await listCreateDocFields(next)).filter((fld) => fld.required).map((fld) => [fld.fieldname, '']));
    } catch { /* the form still works without the head start */ }
    patch({ doctype: next, fields: required });
  };
  const setField = (name: string, value: unknown) => patch({ fields: { ...fields, [name]: value } });
  const removeField = (name: string) => {
    const next = { ...fields };
    delete next[name];
    patch({ fields: next });
  };

  return (
    <Section title={title} hint="Creates a new record, for example a to-do. Your administrator decides which kinds of record flows may create. Details of the new record go to the next step.">
      <div>
        <Label htmlFor="doc-create-doctype" size="sm">Kind of record</Label>
        {typesFailed ? (
          <Input id="doc-create-doctype" data-testid={f('doctype')} value={doctype} onChange={(e) => patch({ doctype: e.target.value })} placeholder="ToDo" />
        ) : (
          <Combobox
            id="doc-create-doctype"
            testId={f('doctype')}
            options={typeOptions}
            value={doctype}
            onValueChange={(v) => void chooseType(v)}
            placeholder={types === null ? 'Loading...' : 'Choose a kind of record...'}
            disabled={types === null}
            searchPlaceholder="Search..."
            emptyText={types && types.length === 0 ? 'Your administrator has not allowed flows to create any records yet.' : 'Nothing matches that. Try another word.'}
          />
        )}
        <FieldHint testId="flow-hint-doc-create-doctype">
          {unlisted ? 'This kind of record is not on the allowed list, so the step will not run. Choose another kind.' : 'What the flow creates each time it reaches this step, for example a To-do. Only the kinds you may create are listed.'}
        </FieldHint>
        <Err field="doctype" />
      </div>
      {doctype && (
        <div className="space-y-3" data-testid={f('fields')}>
          <Label size="sm">What to fill in</Label>
          {entries.length === 0 && <FieldHint testId="flow-hint-doc-create-empty">Nothing yet. Add the fields you want to fill in.</FieldHint>}
          {entries.map(([name, val], i) => {
            const fld = byName.get(name);
            const label = fld?.label ?? name;
            return (
              <div key={name} className="space-y-1.5 rounded-md border border-border p-2" data-testid={`flow-doc-field-${name}`}>
                <div className="flex items-center gap-2">
                  <span className="min-w-0 flex-1 truncate text-sm font-medium" data-testid={f(`fields.${i}.name`)}>
                    {label}
                    {fld?.required ? <span className="text-meta font-normal text-muted-foreground"> (needed)</span> : null}
                  </span>
                  <Button type="button" variant="ghost" size="sm" aria-label={`Remove ${label}`} data-testid={f(`fields.${i}.remove`)} onClick={() => removeField(name)}>
                    <X className="h-4 w-4" />
                  </Button>
                </div>
                {fieldList && !fld ? (
                  <p className="text-meta text-destructive" role="alert">This is not a field of this record, so the step cannot run. Remove it.</p>
                ) : fld?.kind === 'choice' && typeof val === 'string' && (fld.options.includes(val) || val === '') ? (
                  <Select value={val} onValueChange={(v) => setField(name, v)}>
                    <SelectTrigger aria-label={label} data-testid={f(`fields.${i}.value`)}><SelectValue placeholder="Choose..." /></SelectTrigger>
                    <SelectContent>
                      {fld.options.map((o) => <SelectItem key={o} value={o}>{o}</SelectItem>)}
                    </SelectContent>
                  </Select>
                ) : (
                  <DataInput
                    id={`doc-field-${i}-value`}
                    nodeId={nodeId}
                    testId={f(`fields.${i}.value`)}
                    kind={fld?.kind === 'longtext' ? 'longtext' : fld?.kind === 'number' ? 'number' : fld?.kind === 'yesno' ? 'yesno' : 'text'}
                    placeholder={fld?.kind === 'date' ? '2026-10-29' : undefined}
                    hint={fld ? KIND_HINT[fld.kind] || undefined : undefined}
                    value={val}
                    onChange={(v) => setField(name, v === undefined ? '' : v)}
                  />
                )}
              </div>
            );
          })}
          {fieldList === null ? (
            <p className="text-meta text-muted-foreground">Loading the fields...</p>
          ) : addable.length > 0 ? (
            <Combobox
              testId={f('fields.add')}
              options={addable.map((fld) => ({ value: fld.fieldname, label: fld.label, subtitle: fld.required ? 'Needed' : undefined }))}
              value=""
              onValueChange={(v) => v && setField(v, '')}
              placeholder="Add a field..."
              searchPlaceholder="Search fields..."
              emptyText="No more fields."
            />
          ) : null}
          <FieldHint testId="flow-hint-doc-create-fields">Pick a field by its name and give it a value. Use + Use data to fill it from an earlier step.</FieldHint>
        </div>
      )}
    </Section>
  );
}
