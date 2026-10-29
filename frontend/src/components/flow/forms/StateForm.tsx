import { FieldHint } from '../FieldHint';
import { FlowValueInput } from '../../FlowValueInput';
import { Input } from '../../ui/input';
import { Label } from '../../ui/label';
import { type ActionFormProps, Section, str } from './formKit';

export function StateForm({ nodeId, cfg, patch, f, Err, title }: ActionFormProps) {
  const type = str(cfg.type);

  return (
    <Section title={title} hint={type === 'state-get' ? 'Reads a value this flow saved earlier (in this or a previous run). It becomes the result of the step. Values belong to this flow only.' : type === 'state-set' ? 'Saves a value under a key so this flow can read it later, even in another run. Values belong to this flow only. Use a template to key by sender, for example cart:{sender}.' : 'Removes a value this flow saved earlier. Nothing happens if the key does not exist.'}>
      <div>
        <FlowValueInput id="state-key" nodeId={nodeId} testId={f('key')} label="Key" placeholder="cart:42" hint="The name the value is saved under. Reading it later needs the same key." value={cfg.key} onChange={(v) => patch({ key: v })} />
        <Err field="key" />
      </div>
      {type === 'state-get' && <FlowValueInput id="state-default" nodeId={nodeId} testId={f('default')} label="Default" optional hint="Returned when nothing is saved under this key." value={cfg.default} onChange={(v) => patch({ default: v })} />}
      {type === 'state-set' && (
        <>
          <div>
            <FlowValueInput id="state-value" nodeId={nodeId} testId={f('value')} label="Value" hint="What to save. Use Insert data to save something from an earlier step." value={cfg.value} onChange={(v) => patch({ value: v })} />
            <Err field="value" />
          </div>
          <div>
            <Label htmlFor="state-ttl" size="sm">Keep for (seconds, optional, max 2592000)</Label>
            <Input
              id="state-ttl"
              data-testid={f('ttl_seconds')}
              type="number"
              min={1}
              max={2592000}
              value={typeof cfg.ttl_seconds === 'number' ? cfg.ttl_seconds : ''}
              onChange={(e) => patch({ ttl_seconds: e.target.value === '' ? undefined : parseInt(e.target.value, 10) })}
              placeholder="Keep until deleted"
            />
            <FieldHint testId="flow-hint-state-ttl">After this many seconds the value is forgotten. 3600 is one hour, 86400 is one day.</FieldHint>
          </div>
        </>
      )}
    </Section>
  );
}
