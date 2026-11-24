import { useEffect, useState } from 'react';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { listTriggerDoctypes, type TriggerDoctype } from '@/services/flow/triggerApi';
import { DoctypePicker } from '../../DoctypePicker';
import { FieldHint } from '../../FieldHint';
import { Input } from '../../../ui/input';
import { Label } from '../../../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../ui/select';
import { KeyValueRows, ValueField } from '../fields';
import { type ActionFormProps, Section } from '../formKit';

/** The document types a step may pick (the same list the document trigger uses). */
export function useDoctypeOptions() {
  const [options, setOptions] = useState<TriggerDoctype[]>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let live = true;
    listTriggerDoctypes().then((l) => live && setOptions(l)).catch(() => live && setOptions([])).finally(() => live && setLoading(false));
    return () => { live = false; };
  }, []);
  return { options, loading };
}

/** Find document: read one document by name or by matching fields, and hand some of its fields on. */
export function DocGetForm({ nodeId, cfg, patch, f, Err, title }: ActionFormProps) {
  const { canManage } = useFlowPermissions();
  const { options, loading } = useDoctypeOptions();
  const byFields = cfg.filters !== undefined;
  const fields = Array.isArray(cfg.fields) ? (cfg.fields as string[]) : [];
  const [fieldsText, setFieldsText] = useState(fields.join(', '));
  return (
    <Section title={title} hint="Reads one document as the person this flow runs as, and gives its fields to the next steps.">
      <div>
        <Label htmlFor="doc-get-doctype" size="sm">Document type</Label>
        <DoctypePicker id="doc-get-doctype" testId={f('doctype')} options={options} loading={loading} disabled={!canManage} value={typeof cfg.doctype === 'string' ? cfg.doctype : ''} onChange={(doctype) => patch({ doctype })} />
        <Err field="doctype" />
      </div>
      <div>
        <Label htmlFor="doc-get-by" size="sm">Find by</Label>
        <Select value={byFields ? 'fields' : 'name'} disabled={!canManage} onValueChange={(v) => (v === 'fields' ? patch({ name: undefined, filters: {} }) : patch({ filters: undefined, name: '' }))}>
          <SelectTrigger id="doc-get-by" data-testid={f('by')}><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="name">Name</SelectItem>
            <SelectItem value="fields">Matching fields</SelectItem>
          </SelectContent>
        </Select>
      </div>
      {byFields ? (
        <div>
          <Label size="sm">Fields to match</Label>
          <KeyValueRows testId={f('filters')} nodeId={nodeId} disabled={!canManage} keyLabel="Field" addLabel="Add a field to match" value={cfg.filters} onChange={(filters) => patch({ filters: filters ?? {} })} />
          <Err field="filters" />
        </div>
      ) : (
        <ValueField field="name" f={f} Err={Err} nodeId={nodeId} label="Document name" disabled={!canManage} value={cfg.name} onChange={(name) => patch({ name })} />
      )}
      <div>
        <Label htmlFor="doc-get-fields" size="sm">Fields to return (optional)</Label>
        <Input
          id="doc-get-fields"
          data-testid={f('fields')}
          disabled={!canManage}
          placeholder="customer_name, status"
          value={fieldsText}
          onChange={(e) => {
            setFieldsText(e.target.value);
            const list = e.target.value.split(',').map((s) => s.trim()).filter(Boolean);
            patch({ fields: list.length ? list : undefined });
          }}
        />
        <FieldHint testId="flow-hint-doc-get-fields">Separate the field names with commas. Leave empty to get just the document name.</FieldHint>
      </div>
      <div>
        <Label htmlFor="doc-get-missing" size="sm">If nothing is found</Label>
        <Select value={cfg.on_missing === 'empty' ? 'empty' : 'error'} disabled={!canManage} onValueChange={(v) => patch({ on_missing: v === 'empty' ? 'empty' : undefined })}>
          <SelectTrigger id="doc-get-missing" data-testid={f('on_missing')}><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="error">Fail the step</SelectItem>
            <SelectItem value="empty">Continue with nothing</SelectItem>
          </SelectContent>
        </Select>
      </div>
    </Section>
  );
}
