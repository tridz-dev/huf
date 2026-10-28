import { ScheduleEditor } from './flow/ScheduleEditor';
import { Label } from './ui/label';
import { Combobox } from './ui/combobox';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { DOC_EVENTS, type FlowDocEvent } from '../lib/flowTrigger';

interface FlowTriggerPanelProps {
  kind: 'schedule' | 'doc-event';
  docTypes: Array<{ value: string; label: string }>;
  loadingDocTypes: boolean;
  /** The node's own config (the contract fields: cron, or doctype + event). The form edits it directly. */
  value: { cron?: string; doctype?: string; event?: string };
  onChange: (patch: Record<string, unknown>) => void;
  /** Inline validation messages by contract field. */
  errors?: Record<string, string | undefined>;
}

const EVENT_LABELS: Record<FlowDocEvent, string> = {
  after_insert: 'When a record is created',
  on_update: 'When a record is updated',
  on_submit: 'When a record is submitted',
  on_cancel: 'When a record is cancelled',
  on_trash: 'When a record is deleted',
};

/**
 * Schedule / document-event trigger editor. The trigger lives entirely in the node's config and goes live
 * when the flow is published; there is nothing to activate separately.
 */
export function FlowTriggerPanel({ kind, docTypes, loadingDocTypes, value, onChange, errors = {} }: FlowTriggerPanelProps) {
  const docForm = {
    referenceDoctype: value.doctype ?? '',
  };

  return (
    <div className="space-y-3">
      {kind === 'schedule' ? (
        <ScheduleEditor
          cron={value.cron}
          error={errors.cron}
          onChange={(cron) => onChange({ cron })}
        />
      ) : (
        <>
          <div>
            <Label htmlFor="doctype">Document type</Label>
            <Combobox
              id="doctype"
              testId="flow-field-trigger.doc-event-doctype"
              options={docTypes}
              value={docForm.referenceDoctype}
              onValueChange={(v) => onChange({ doctype: v })}
              placeholder={loadingDocTypes ? 'Loading...' : 'Select a document type...'}
              disabled={loadingDocTypes}
              searchPlaceholder="Search document types..."
              emptyText="No document type found."
            />
            {errors.doctype ? (
              <p role="alert" className="mt-1 text-[11px] text-destructive" data-testid="flow-error-trigger.doc-event-doctype">{errors.doctype}</p>
            ) : null}
          </div>
          <div>
            <Label htmlFor="doc-event">When it fires</Label>
            <Select value={value.event ?? ''} onValueChange={(v) => onChange({ event: v })}>
              <SelectTrigger id="doc-event" data-testid="flow-field-trigger.doc-event-event">
                <SelectValue placeholder="Choose an event..." />
              </SelectTrigger>
              <SelectContent>
                {DOC_EVENTS.map((e) => (
                  <SelectItem key={e} value={e} data-testid={`flow-option-doc-event-${e}`}>
                    {EVENT_LABELS[e]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {errors.event ? (
              <p role="alert" className="mt-1 text-[11px] text-destructive" data-testid="flow-error-trigger.doc-event-event">{errors.event}</p>
            ) : null}
          </div>
        </>
      )}

    </div>
  );
}
