import { FieldHint } from '../FieldHint';
import { Label } from '../../ui/label';
import { MoreOptions } from '../frame/MoreOptions';
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from '../../ui/select';
import { TRANSFORM_HELP, transformParamHelp } from '@/lib/flow/flowHelp';
import { getTransformOp, TRANSFORM_OPS, TRANSFORM_SECTIONS } from '@/lib/flow-graph/flowTransformOps';
import { type ActionFormProps, asObj, Section, str } from './formKit';
import { ListRows, ValueField } from './fields';
import { useDataCatalog } from '../data/useDataCatalog';
import type { PickerModel } from '@/lib/flow-data/model';

/** Inputs that take a whole list from an earlier step, and inputs that are a short list of values typed in. */
const LIST_PARAMS = new Set(['rows', 'left', 'right', 'from']);
const ROW_PARAMS = new Set(['fields', 'values', 'parts']);
const NUMBER_PARAMS = new Set(['count', 'group', 'size']);
/** Optional inputs that are still part of the main job (replacing with nothing removes the text). */
const MAIN_OPTIONAL = new Set(['with']);
const paramKind = (p: string) => (NUMBER_PARAMS.has(p) ? 'number' : p === 'ignore_case' ? 'yesno' : undefined);

/** What to start a new operation with: the data the step before it produced, when there is a clear choice. */
export function startingData(op: string, model: PickerModel): Record<string, unknown> {
  const spec = getTransformOp(op);
  const first = spec?.params[0];
  // The step right before this one (the trigger when there is none).
  const near = model.steps.find((s) => s.kind === 'step') ?? model.steps.find((s) => s.kind === 'trigger');
  if (!spec || !first || !near) return {};
  if (first === 'text') {
    const field = near.fields.find((f) => f.path && f.type === 'text' && !f.advanced_only);
    if (field?.path) return { text: { $from: field.path } };
    return near.kind === 'step' ? { text: { $from: near.id } } : {};
  }
  if (LIST_PARAMS.has(first) && first !== 'right' && first !== 'from') {
    const list = near.fields.find((f) => f.path && f.type === 'list' && !f.advanced_only);
    if (list?.path) return { [first]: { $from: list.path } };
  }
  return {};
}

export function TransformForm({ nodeId, cfg, patch, f, Err, title }: ActionFormProps) {
  const input = asObj(cfg.input);
  const setInput = (key: string, value: unknown) => patch({ input: { ...input, [key]: value === '' ? undefined : value } });
  const { model } = useDataCatalog(nodeId);

  const spec = getTransformOp(str(cfg.op));
  const opHelp = spec ? TRANSFORM_HELP[spec.name] : undefined;
  const renderParam = (param: string) => {
    if (!spec) return null;
    const ph = transformParamHelp(spec.name, param);
    if (ROW_PARAMS.has(param) && (input[param] === undefined || Array.isArray(input[param]))) {
      return (
        <div key={`${spec.name}-${param}`} className="space-y-1">
          <Label size="sm">{ph.label}</Label>
          <ListRows testId={f(`input.${param}`)} nodeId={nodeId} itemLabel={param === 'fields' ? 'Field' : param === 'parts' ? 'Part' : 'Value'} placeholder={ph.placeholder} addLabel={param === 'fields' ? 'Add a field' : param === 'parts' ? 'Add a part' : 'Add a value'} value={input[param]} onChange={(v) => setInput(param, v)} />
          {ph.hint ? <FieldHint>{ph.hint}</FieldHint> : null}
          <Err field={`input.${param}`} />
        </div>
      );
    }
    return (
      <ValueField
        key={`${spec.name}-${param}`}
        field={`input.${param}`}
        f={f}
        Err={Err}
        nodeId={param === 'where' ? '' : nodeId}
        label={ph.label}
        placeholder={ph.placeholder}
        hint={ph.hint}
        optional={spec.optional?.includes(param) && !MAIN_OPTIONAL.has(param)}
        kind={paramKind(param)}
        accept={LIST_PARAMS.has(param) ? 'list' : undefined}
        value={input[param]}
        onChange={(v) => setInput(param, v)}
      />
    );
  };
  const mainParams = spec?.params.filter((p) => !spec.optional?.includes(p) || MAIN_OPTIONAL.has(p)) ?? [];
  const moreParams = spec?.params.filter((p) => spec.optional?.includes(p) && !MAIN_OPTIONAL.has(p)) ?? [];
  return (
    <Section title={title} hint="Changes data without any AI: text, lists and records. The result goes to the next step.">
      <div>
        <Label htmlFor="transform-op" size="sm">What to do</Label>
        <Select value={str(cfg.op)} onValueChange={(v) => patch({ op: v, input: model ? startingData(v, model) : {} })}>
          <SelectTrigger id="transform-op" data-testid={f('op')}>
            <SelectValue placeholder="Choose what to do with the data..." />
          </SelectTrigger>
          <SelectContent className="max-h-[min(24rem,var(--radix-select-content-available-height))]">
            {TRANSFORM_SECTIONS.map((sec) => (
              <SelectGroup key={sec.id} data-testid={`flow-transform-group-${sec.id}`}>
                <SelectLabel>{sec.title}</SelectLabel>
                {TRANSFORM_OPS.filter((o) => o.section === sec.id).map((o) => (
                  <SelectItem key={o.name} value={o.name} description={TRANSFORM_HELP[o.name]?.example} data-testid={`flow-option-transform-op-${o.name}`}>{o.label}</SelectItem>
                ))}
              </SelectGroup>
            ))}
          </SelectContent>
        </Select>
        {opHelp ? (
          <div data-testid="flow-hint-transform-op">
            <FieldHint>{opHelp.summary}</FieldHint>
            <FieldHint className="italic" testId="flow-hint-transform-example">Example: {opHelp.example}</FieldHint>
          </div>
        ) : (
          <FieldHint testId="flow-hint-transform-op">Pick what to do and you will see what it does, with a small example.</FieldHint>
        )}
        <Err field="op" />
      </div>
      {mainParams.map(renderParam)}
      {moreParams.length > 0 && (
        <MoreOptions defaultOpen={moreParams.some((p) => input[p] !== undefined && input[p] !== '')} testId="flow-more-options-transform">
          {moreParams.map(renderParam)}
        </MoreOptions>
      )}
    </Section>
  );
}
