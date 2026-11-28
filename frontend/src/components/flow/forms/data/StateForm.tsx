import { MoreOptions } from '../../frame/MoreOptions';
import { type ActionFormProps, Section, str } from '../formKit';
import { useEffect, useState } from 'react';
import { Label } from '../../../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../ui/select';
import { ValueField } from '../fields';
import { getFlowStateLimits } from '@/services/flow/steps/flowMembersApi';
import { KEEP_OPTIONS, keepAllowed, keepLimitReason, keepValueOf } from '@/lib/flow-data/stateKeep';

const HINT = {
  'state-get': 'Looks up something this flow saved earlier, in this run or an earlier one. It becomes the result of this step. Saved data belongs to this flow only.',
  'state-set': 'Saves something so this flow can look it up later, even in another run. Saved data belongs to this flow only.',
  'state-delete': 'Forgets something this flow saved earlier. Nothing happens if there is nothing saved under that name.',
} as const;

export function StateForm({ nodeId, cfg, patch, f, Err, title }: ActionFormProps) {
  const type = str(cfg.type) as keyof typeof HINT;
  const keyLabel = type === 'state-get' ? 'Name it was saved under' : type === 'state-delete' ? 'Name of the saved data' : 'Save it under the name';
  const [maxTtl, setMaxTtl] = useState<number | null>(null);
  useEffect(() => {
    if (type !== 'state-set') return;
    let live = true;
    getFlowStateLimits().then((l) => live && setMaxTtl(l.max_ttl_seconds)).catch(() => {});
    return () => { live = false; };
  }, [type]);
  const foreverBlocked = maxTtl !== null && !keepAllowed(0, maxTtl);
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
        <div>
          <Label htmlFor="state-keep">Keep saved data for</Label>
          <Select value={keepValueOf(cfg.ttl_seconds) ?? undefined} onValueChange={(v) => { const o = KEEP_OPTIONS.find((k) => k.value === v)!; patch({ ttl_seconds: o.value === 'day' ? undefined : o.seconds }); }}>
            <SelectTrigger id="state-keep" aria-label="Keep saved data for" data-testid={f('ttl_seconds')}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {KEEP_OPTIONS.map((o) => <SelectItem key={o.value} value={o.value} disabled={!keepAllowed(o.seconds, maxTtl)}>{o.label}</SelectItem>)}
            </SelectContent>
          </Select>
          {foreverBlocked && <p className="mt-1.5 text-xs text-muted-foreground" data-testid="flow-state-keep-limit">{keepLimitReason(maxTtl!)}</p>}
        </div>
      )}
    </Section>
  );
}
