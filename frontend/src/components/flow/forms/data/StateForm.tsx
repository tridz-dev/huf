import { FieldHint } from '../../FieldHint';
import { MoreOptions } from '../../frame/MoreOptions';
import { type ActionFormProps, Section, str } from '../formKit';
import { DurationField, ValueField } from '../fields';
import type { TimeUnit } from '@/lib/flow-data/flowUnits';

const TTL_UNITS: TimeUnit[] = ['minutes', 'hours', 'days'];
const MAX_TTL_SECONDS = 2592000;

const HINT = {
  'state-get': 'Looks up something this flow saved earlier, in this run or an earlier one. It becomes the result of this step. Saved data belongs to this flow only.',
  'state-set': 'Saves something so this flow can look it up later, even in another run. Saved data belongs to this flow only.',
  'state-delete': 'Forgets something this flow saved earlier. Nothing happens if there is nothing saved under that name.',
} as const;

export function StateForm({ nodeId, cfg, patch, f, Err, title }: ActionFormProps) {
  const type = str(cfg.type) as keyof typeof HINT;
  const keyLabel = type === 'state-get' ? 'Name it was saved under' : type === 'state-delete' ? 'Name of the saved data' : 'Save it under the name';
  const ttlIsData = cfg.ttl_seconds !== undefined && typeof cfg.ttl_seconds !== 'number';
  return (
    <Section title={title} hint={HINT[type] ?? HINT['state-set']}>
      <ValueField
        field="key"
        f={f}
        Err={Err}
        nodeId={nodeId}
        label={keyLabel}
        placeholder="cart-42"
        hint="A short name you will use to find it again, like last-order. To keep one per customer, add the customer's ID to the name with + Use data."
        value={cfg.key}
        onChange={(v) => patch({ key: v })}
      />
      {type === 'state-set' && (
        <ValueField
          field="value"
          f={f}
          Err={Err}
          nodeId={nodeId}
          label="What to save"
          kind="longtext"
          placeholder="For example the order total"
          hint="Type a value, or use + Use data to save something from an earlier step."
          value={cfg.value}
          onChange={(v) => patch({ value: v })}
        />
      )}
      {type === 'state-get' && (
        <MoreOptions defaultOpen={cfg.default !== undefined && cfg.default !== ''} testId="flow-more-options-state">
          <ValueField field="default" f={f} Err={Err} nodeId={nodeId} label="If nothing is saved" optional placeholder="Nothing" hint="Used when there is nothing saved under that name yet." value={cfg.default} onChange={(v) => patch({ default: v })} />
        </MoreOptions>
      )}
      {type === 'state-set' && (
        <MoreOptions defaultOpen={cfg.ttl_seconds !== undefined} testId="flow-more-options-state">
          {ttlIsData ? (
            <ValueField field="ttl_seconds" f={f} Err={Err} nodeId={nodeId} label="Keep it for (seconds)" kind="number" optional value={cfg.ttl_seconds} onChange={(v) => patch({ ttl_seconds: v === '' ? undefined : v })} />
          ) : (
            <div>
              <DurationField
                id="state-ttl"
                testId={f('ttl_seconds')}
                label="Keep it for"
                units={TTL_UNITS}
                placeholder="Until I forget it"
                value={typeof cfg.ttl_seconds === 'number' ? cfg.ttl_seconds : undefined}
                onChange={(s) => patch({ ttl_seconds: s === undefined ? undefined : Math.min(s, MAX_TTL_SECONDS) })}
                hint="After this long it is forgotten. Leave empty to keep it until a Forget saved data step removes it. The longest is 30 days."
              />
              <FieldHint testId="flow-hint-state-ttl-max">Examples: 30 minutes, 12 hours, 7 days.</FieldHint>
            </div>
          )}
        </MoreOptions>
      )}
    </Section>
  );
}
