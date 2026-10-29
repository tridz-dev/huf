import { useEffect, useRef, useState } from 'react';
import { FieldHint, Examples } from '../FieldHint';
import { DoctypePicker } from '../DoctypePicker';
import { Label } from '../../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../ui/select';
import { DOC_EVENTS, EVENT_WORD, type FlowDocEvent } from '@/lib/flow-graph/flowTrigger';
import { DOC_EVENT_HELP } from '@/lib/flow/flowHelp';
import { getTriggerDoctypeInfo } from '@/services/flowApi';
import { listTriggerDoctypes, type TriggerDoctype } from '@/services/flowTriggerApi';
import { str, useNodeForm } from './formKit';

const EVERYDAY: FlowDocEvent[] = ['after_insert', 'on_update', 'on_trash'];

/**
 * "When a [document type] is [created]": a sentence builder. The event starts as "created", nothing is red until the person
 * has been to the field, and submit / cancel only appear for document types that can be submitted.
 */
export function DataTriggerForm({ nodeId }: { nodeId: string }) {
  const { cfg, patch, shell, kind } = useNodeForm(nodeId, 'triggerConfig');
  const doctype = str(cfg.doctype);
  const event = str(cfg.event) as FlowDocEvent | '';
  const [options, setOptions] = useState<TriggerDoctype[]>([]);
  const [loading, setLoading] = useState(true);
  const [touchedType, setTouchedType] = useState(false);
  const [submittable, setSubmittable] = useState<{ doctype: string; yes: boolean } | null>(null);
  const [resetNote, setResetNote] = useState<string | null>(null);
  const eventRef = useRef(event);
  eventRef.current = event;

  useEffect(() => {
    let cancelled = false;
    listTriggerDoctypes()
      .then((l) => !cancelled && setOptions(l))
      .catch(() => !cancelled && setOptions([]))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  // The most common choice is already made.
  useEffect(() => {
    if (!event) patch({ event: 'after_insert' });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!doctype) {
      setSubmittable(null);
      return;
    }
    let cancelled = false;
    getTriggerDoctypeInfo(doctype)
      .then((info) => {
        if (cancelled) return;
        setSubmittable({ doctype, yes: info.is_submittable });
        const current = eventRef.current;
        if (!info.is_submittable && (current === 'on_submit' || current === 'on_cancel')) {
          const name = options.find((o) => o.name === doctype)?.label ?? doctype;
          setResetNote(`"${EVENT_WORD[current]}" is not available for ${name}, because it cannot be submitted. It is set back to "created".`);
          patch({ event: 'after_insert' });
        }
      })
      .catch(() => !cancelled && setSubmittable(null));
    return () => {
      cancelled = true;
    };
    // patch is a fresh closure every render; the document type is the only input that should refetch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doctype]);

  const knownSubmittable = submittable !== null && submittable.doctype === doctype && submittable.yes;
  const events = DOC_EVENTS.filter((e) => EVERYDAY.includes(e) || knownSubmittable || e === event);
  const typeError = touchedType ? shell.error('doctype') : undefined;
  const picked = options.find((o) => o.name === doctype);
  const help = event && DOC_EVENT_HELP[event] ? DOC_EVENT_HELP[event] : DOC_EVENT_HELP.after_insert;

  return (
    <div className="space-y-3" data-testid="flow-data-trigger">
      <p className="text-xs text-muted-foreground" data-testid="flow-hint-doc-event-intro">
        Starts the flow when something is added, changed or deleted in your data. It only runs while the flow is live. The details of the record are available to the steps that follow.
      </p>

      <div className="grid grid-cols-[3.5rem_minmax(0,1fr)] items-center gap-x-2 gap-y-3" data-testid="flow-data-sentence">
        <Label htmlFor="doctype" size="sm" className="text-right">When a</Label>
        <div>
          <DoctypePicker
            id="doctype"
            testId="flow-field-trigger.doc-event-doctype"
            options={options}
            value={doctype}
            loading={loading}
            onChange={(name) => {
              setResetNote(null);
              setTouchedType(true);
              patch({ doctype: name });
            }}
            onClosed={(hasValue) => !hasValue && setTouchedType(true)}
          />
        </div>
        <Label htmlFor="doc-event" size="sm" className="text-right">is</Label>
        <Select
          value={event || 'after_insert'}
          onValueChange={(v) => {
            setResetNote(null);
            patch({ event: v });
          }}
        >
          <SelectTrigger id="doc-event" data-testid="flow-field-trigger.doc-event-event">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {events.map((e) => (
              <SelectItem key={e} value={e} data-testid={`flow-option-doc-event-${e}`}>
                {EVENT_WORD[e]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {picked && <FieldHint testId="flow-hint-doc-event-doctype">Watching: {picked.label}{picked.module && picked.group === 'apps' ? ` (${picked.module})` : ''}.</FieldHint>}
      {typeError ? (
        <p role="alert" className="text-meta text-destructive" data-testid={`flow-error-${kind}-doctype`}>{typeError}</p>
      ) : null}
      <FieldHint testId="flow-hint-doc-event-event">{help}</FieldHint>
      <Examples testId="flow-doc-event-explained" title="What each choice means">
        {events.map((e) => (
          <p key={e}><strong>{EVENT_WORD[e]}.</strong> {DOC_EVENT_HELP[e]}</p>
        ))}
      </Examples>
      {resetNote ? (
        <p role="status" className="text-meta text-signal-ink" data-testid="flow-doc-event-reset-note">{resetNote}</p>
      ) : null}

      <div className="rounded-md border border-dashed border-line px-2.5 py-2 text-xs text-muted-foreground" data-testid="flow-doc-event-filter">
        <span className="font-medium text-ink">Only when...</span> <span className="rounded bg-muted px-1.5 py-0.5">Coming soon</span>
        <p className="mt-0.5">Limiting this to records that match, for example only when Status is Open, is not available yet. For now the flow starts for every record.</p>
      </div>
    </div>
  );
}
