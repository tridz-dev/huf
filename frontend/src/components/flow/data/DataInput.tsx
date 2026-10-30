import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { Button } from '../../ui/button';
import { Label } from '../../ui/label';
import { Popover, PopoverAnchor, PopoverContent } from '../../ui/popover';
import { useFlowContext } from '@/contexts/FlowContext';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { useViewport } from '@/lib/ui/responsive';
import { getLastWebhookRequest } from '@/services/flow/triggerApi';
import { cn } from '@/lib/utils';
import type { RefScope } from '@/lib/flow/flowRefs';
import {
  chipBefore, chipNames, makeChip, parseValue, serializeValue, uniqueVariable, type Chip, type ParsedValue, type Segment,
} from '@/lib/flow-data/chips';
import { describeChip, previewOf, type PickerStep } from '@/lib/flow-data/model';
import type { DataPick } from '@/lib/flow-data/types';
import { ChipEditor, type ChipEditorHandle } from './ChipEditor';
import { DataPicker } from './DataPicker';
import { JsonDataInput } from './JsonDataInput';
import { YesNoInput } from './YesNoInput';
import { invalidateDataCatalog, useDataCatalog } from './useDataCatalog';

export type DataKind = 'text' | 'longtext' | 'number' | 'url' | 'json' | 'yesno';

export interface DataInputProps {
  value: unknown;
  onChange: (value: unknown) => void;
  /** The step this field belongs to: decides which earlier steps can be used. */
  nodeId?: string;
  kind?: DataKind;
  placeholder?: string;
  /** One line under the box: where to find the value. */
  hint?: string;
  /** Test id of the box; the "+ Use data" button is `<testId>-picker` and the preview `<testId>-preview`. */
  testId?: string;
  id?: string;
  label?: string;
  optional?: boolean;
  /**
   * `list`: the field takes a whole list (a loop's items); picking a list sets it directly.
   * `one`: the field takes exactly one thing from an earlier step (a loop's "result to collect"); a pick sets it directly.
   * Both are pick-only: typing is not possible, because what is stored is a reference.
   */
  accept?: 'value' | 'list' | 'one';
  /** `loop-body`: the steps inside this loop (for a loop's "result to collect"). */
  scope?: RefScope;
  disabled?: boolean;
}

/** A number or Yes/No typed into a text box is shown as its words; only a list or an object is shown as JSON. */
const asText = (value: unknown) => (typeof value === 'number' || typeof value === 'boolean' ? String(value) : value);

const DEFAULT_PLACEHOLDER = 'Type, or press / to use data';

/**
 * The one input for a value in a flow step: type text, add data from earlier steps as chips, or both. What is stored
 * (a plain text, a reference, or a template) is worked out from what is on screen; nobody chooses a "mode".
 * A value that is a list or an object (an old flow, or `kind="json"`) is shown as "Advanced (JSON)".
 */
export function DataInput(props: DataInputProps) {
  const { kind = 'text', value } = props;
  if (kind === 'yesno') return <YesNoInput {...props} />;
  const isOther = parseValue(asText(value)).form === 'other';
  // Once a box is in JSON it stays there while it is being edited (half-typed JSON is not a list yet).
  const [asJson, setAsJson] = useState(isOther);
  useEffect(() => {
    if (isOther) setAsJson(true);
  }, [isOther]);
  if (kind === 'json' || asJson) {
    return <JsonDataInput {...props} forced={kind === 'json'} onUseText={() => { setAsJson(false); props.onChange(''); }} />;
  }
  return <ChipField {...props} />;
}

function ChipField({ value, onChange, nodeId, kind = 'text', placeholder, hint, testId, id, label, optional, accept = 'value', scope, disabled }: DataInputProps) {
  const autoId = useId();
  const inputId = id ?? autoId;
  const hintId = `${inputId}-hint`;
  const previewId = `${inputId}-preview`;
  const { canManage } = useFlowPermissions();
  const { activeFlow, updateNodeData } = useFlowContext();
  const { isPhone } = useViewport();
  // A form switched off from outside (a phone only reads the step; view-only people) is read here too.
  const wrap = useRef<HTMLDivElement>(null);
  const [locked, setLocked] = useState(false);
  useLayoutEffect(() => {
    const now = !!wrap.current?.closest('fieldset:disabled');
    setLocked((prev) => (prev === now ? prev : now));
  });
  const editable = canManage && !disabled && !locked;
  const { model, loading, refresh } = useDataCatalog(nodeId, scope);
  const editor = useRef<ChipEditorHandle>(null);

  const normalized = asText(value);
  const [state, setState] = useState<ParsedValue>(() => parseValue(normalized));
  const [version, setVersion] = useState(0);
  const sent = useRef(JSON.stringify(value ?? null));
  useEffect(() => {
    const key = JSON.stringify(value ?? null);
    if (key === sent.current) return;
    sent.current = key;
    setState(parseValue(normalized));
    setVersion((v) => v + 1);
  }, [value, normalized]);

  const describe = (chip: Chip) => describeChip(chip, model);
  const chipInfoKey = state.segments.flatMap((s) => (s.kind === 'chip' ? [JSON.stringify(describe(s.chip))] : [])).join('|');
  const drawKey = `${version}|${editable}|${chipInfoKey}`;

  const send = (segments: Segment[], base: ParsedValue) => {
    const out = serializeValue({ segments, extraVars: base.extraVars, hadVars: base.hadVars }, { kind: kind === 'number' ? 'number' : 'text' });
    sent.current = JSON.stringify(out ?? null);
    onChange(out);
  };
  const onSegments = (segments: Segment[]) => {
    const next: ParsedValue = { ...state, segments, form: 'text' };
    setState(next);
    send(segments, next);
  };

  // ---- the picker ----
  const [open, setOpen] = useState(false);
  const isOpen = useRef(false);
  const [openCount, setOpenCount] = useState(0); // a fresh picker every time it opens, even when the last one is still fading out
  isOpen.current = open;
  const origin = useRef<{ by: 'button' | 'slash' | 'chip'; position: number; chipId?: string; picked: boolean }>({ by: 'button', position: 0, picked: false });
  const openPicker = (by: 'button' | 'slash' | 'chip', chipId?: string) => {
    const position = editor.current?.position() ?? 0;
    origin.current = { by, position, chipId, picked: false };
    refresh();
    isOpen.current = true;
    setOpenCount((c) => c + 1);
    setOpen(true);
  };
  const openFromSlash = (position: number) => {
    openPicker('slash');
    origin.current.position = position;
    return true;
  };
  const closePicker = (next: boolean) => {
    if (!next && !isOpen.current) return; // asked twice (Esc and focus leaving): act once
    isOpen.current = next;
    setOpen(next);
    if (!next && origin.current.by === 'slash' && !origin.current.picked) editor.current?.insertText('/', origin.current.position);
  };

  const onPick = (pick: DataPick) => {
    origin.current.picked = true;
    isOpen.current = false;
    setOpen(false);
    if (accept === 'list' || accept === 'one') {
      const next = { $from: pick.ref };
      sent.current = JSON.stringify(next);
      setState(parseValue(next));
      setVersion((v) => v + 1);
      onChange(next);
      return;
    }
    const taken = chipNames(state.segments);
    const same = state.segments.find((s): s is Extract<Segment, { kind: 'chip' }> => s.kind === 'chip' && s.chip.ref === pick.ref && s.chip.mode === pick.mode);
    const chip = makeChip(pick.ref, pick.label, pick.mode);
    chip.name = same ? same.chip.name : uniqueVariable(chip.name, taken);
    const { chipId, position } = origin.current;
    if (chipId) editor.current?.replace(chipId, chip);
    else if (chipBefore(state.segments, position)) {
      // Two chips side by side would read as one word ("Ada Lovelace450"): put a space between them.
      editor.current?.insertText(' ', position);
      editor.current?.insert(chip, position + 1);
    } else editor.current?.insert(chip, position);
  };

  const fetchLast = async (step: PickerStep) => {
    if (!activeFlow) return;
    const last = await getLastWebhookRequest(activeFlow.id);
    if (!last.found || !last.sample) {
      toast.message('No request has reached this webhook yet. Send one, then try again.');
      return;
    }
    updateNodeData(step.id, (data) => ({ ...data, sample: last.sample as Record<string, unknown> }));
    invalidateDataCatalog();
    toast.success('Now using the last real request as the example.');
  };

  const notANumber = kind === 'number' && typeof value === 'string' && value.trim() !== '';
  const chips = state.segments.some((s) => s.kind === 'chip');
  const preview = chips ? previewOf(state.segments, model) : null;
  const multiline = kind === 'longtext';
  const ph = placeholder ?? (nodeId ? (accept === 'value' ? DEFAULT_PLACEHOLDER : 'Choose with + Use data') : undefined);

  return (
    <div ref={wrap} className="space-y-1" data-testid={testId ? `${testId}-box` : undefined}>
      {label ? (
        <Label htmlFor={inputId} size="sm" className="block min-w-0 truncate">
          {label}
          {optional ? ' (optional)' : ''}
        </Label>
      ) : null}
      <Popover open={open} onOpenChange={closePicker}>
        <PopoverAnchor asChild>
          <div
            className={cn(
              'relative flex rounded border border-input bg-transparent transition-colors focus-within:border-signal focus-within:ring-[3px] focus-within:ring-signal/[.14]',
              !canManage && 'opacity-70'
            )}
          >
            <ChipEditor
              ref={editor}
              id={inputId}
              testId={testId}
              segments={state.segments}
              drawKey={drawKey}
              describe={describe}
              onSegments={onSegments}
              multiline={multiline}
              pickOnly={accept !== 'value'}
              editable={editable}
              placeholder={ph}
              ariaLabel={label}
              ariaDescribedBy={[hint ? hintId : '', preview ? previewId : ''].filter(Boolean).join(' ') || undefined}
              inputMode={kind === 'number' ? 'decimal' : kind === 'url' ? 'url' : 'text'}
              onSlash={editable && nodeId ? (position) => openFromSlash(position) : undefined}
              onChipClick={nodeId ? (chip) => openPicker('chip', chip.id) : undefined}
              className={cn('flex-1', editable && nodeId && 'pr-[5.5rem]')}
            />
            {editable && nodeId ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="absolute right-1 top-1 text-signal-ink"
                aria-label={`Use data in ${label ?? 'this field'}`}
                aria-haspopup="dialog"
                aria-expanded={open}
                data-testid={testId ? `${testId}-picker` : 'flow-use-data-button'}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => openPicker('button')}
              >
                + Use data
              </Button>
            ) : null}
          </div>
        </PopoverAnchor>
        <PopoverContent
          side={isPhone ? 'top' : 'left'}
          align="start"
          sideOffset={12}
          collisionPadding={12}
          className="w-[340px] max-w-[calc(100vw-24px)] p-0 data-[state=closed]:!animate-none"
          onCloseAutoFocus={(e) => {
            e.preventDefault();
            // Not when the picker was opened again while this one was still fading out: that would pull the focus out of the new one.
            if (!isOpen.current) editor.current?.focus();
          }}
        >
          <DataPicker key={openCount} model={model} accept={accept === 'list' ? 'list' : 'value'} onPick={onPick} onFetchLast={fetchLast} loading={loading} />
        </PopoverContent>
      </Popover>
      {hint ? (
        <p id={hintId} className="text-meta leading-snug text-muted-foreground break-words" data-testid={testId ? `${testId}-hint` : undefined}>
          {hint}
        </p>
      ) : null}
      {notANumber ? (
        <p role="alert" className="text-meta leading-snug text-destructive" data-testid={testId ? `${testId}-not-a-number` : undefined}>
          Enter a number, for example 5.
        </p>
      ) : null}
      {preview ? (
        <p id={previewId} aria-live="polite" className="text-meta leading-snug text-muted-foreground break-words" data-testid={testId ? `${testId}-preview` : 'flow-data-preview'}>
          <span className="font-medium">What this will become: </span>
          <span data-testid={testId ? `${testId}-preview-text` : undefined}>{preview.text || 'nothing yet'}</span>
        </p>
      ) : null}
    </div>
  );
}
