import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { DoctypePicker } from '../../DoctypePicker';
import { FieldHint } from '../../FieldHint';
import { Label } from '../../../ui/label';
import { KeyValueRows, ValueField } from '../fields';
import { type ActionFormProps, Section } from '../formKit';
import { useDoctypeOptions } from './DocGetForm';

/** Update document: change fields on one existing document. */
export function DocUpdateForm({ nodeId, cfg, patch, f, Err, title }: ActionFormProps) {
  const { canManage } = useFlowPermissions();
  const { options, loading } = useDoctypeOptions();
  return (
    <Section title={title} hint="Saves the document as the person this flow runs as. Submitted documents cannot be changed here.">
      <div>
        <Label htmlFor="doc-update-doctype" size="sm">Document type</Label>
        <DoctypePicker id="doc-update-doctype" testId={f('doctype')} options={options} loading={loading} disabled={!canManage} value={typeof cfg.doctype === 'string' ? cfg.doctype : ''} onChange={(doctype) => patch({ doctype })} />
        <Err field="doctype" />
      </div>
      <ValueField field="name" f={f} Err={Err} nodeId={nodeId} label="Document name" disabled={!canManage} value={cfg.name} onChange={(name) => patch({ name })} />
      <div>
        <Label size="sm">Fields to change</Label>
        <KeyValueRows testId={f('values')} nodeId={nodeId} disabled={!canManage} keyLabel="Field" addLabel="Add a field to change" value={cfg.values} onChange={(values) => patch({ values: values ?? {} })} />
        <FieldHint testId="flow-hint-doc-update-values">Use the field's name, for example status. Use + Use data to fill it from an earlier step.</FieldHint>
        <Err field="values" />
      </div>
    </Section>
  );
}
