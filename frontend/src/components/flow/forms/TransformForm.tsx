import { FieldHint } from '../FieldHint';
import { FlowValueInput } from '../../FlowValueInput';
import { Label } from '../../ui/label';
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from '../../ui/select';
import { TRANSFORM_HELP, transformParamHelp } from '@/lib/flow/flowHelp';
import { getTransformOp, TRANSFORM_OPS, TRANSFORM_SECTIONS } from '@/lib/flow-graph/flowTransformOps';
import { type ActionFormProps, asObj, Section, str } from './formKit';

/** Inputs that take a whole list from an earlier step, and inputs that are a list or a set of named values typed in. */
const LIST_PARAMS = new Set(['rows', 'left', 'right', 'from']);
const JSON_PARAMS = new Set(['fields', 'where', 'values', 'parts']);
const NUMBER_PARAMS = new Set(['count', 'group', 'size']);
const paramKind = (p: string) => (JSON_PARAMS.has(p) ? 'json' : NUMBER_PARAMS.has(p) ? 'number' : p === 'ignore_case' ? 'yesno' : undefined);

export function TransformForm({ nodeId, cfg, patch, f, Err, title }: ActionFormProps) {
  const input = asObj(cfg.input);
  const setInput = (key: string, value: unknown) => patch({ input: { ...input, [key]: value } });

  const spec = getTransformOp(str(cfg.op));
  const opHelp = spec ? TRANSFORM_HELP[spec.name] : undefined;
  return (
    <Section title={title} hint="Changes data without any AI: text, lists and records. The result goes to the next step.">
      <div>
        <Label htmlFor="transform-op" size="sm">What to do</Label>
        <Select value={str(cfg.op)} onValueChange={(v) => patch({ op: v, input: {} })}>
          <SelectTrigger id="transform-op" data-testid={f('op')}>
            <SelectValue placeholder="Choose an operation..." />
          </SelectTrigger>
          <SelectContent>
            {TRANSFORM_SECTIONS.map((sec) => (
              <SelectGroup key={sec.id} data-testid={`flow-transform-group-${sec.id}`}>
                <SelectLabel>{sec.title}</SelectLabel>
                {TRANSFORM_OPS.filter((o) => o.section === sec.id).map((o) => (
                  <SelectItem key={o.name} value={o.name} data-testid={`flow-option-transform-op-${o.name}`}>{o.label}</SelectItem>
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
          <FieldHint testId="flow-hint-transform-op">Pick an operation to see what it does, with an example.</FieldHint>
        )}
        <Err field="op" />
      </div>
      {spec?.params.map((param) => {
        const ph = transformParamHelp(spec.name, param);
        return (
        <div key={`${spec.name}-${param}`}>
          <FlowValueInput id={`transform-in-${param}`} nodeId={nodeId} testId={f(`input.${param}`)} label={ph.label} placeholder={ph.placeholder} hint={ph.hint} optional={spec.optional?.includes(param)} kind={paramKind(param)} accept={LIST_PARAMS.has(param) ? 'list' : undefined} value={input[param]} onChange={(v) => setInput(param, v)} />
          <Err field={`input.${param}`} />
        </div>
        );
      })}
    </Section>
  );
}
