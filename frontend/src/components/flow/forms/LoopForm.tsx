import { FieldHint } from '../FieldHint';
import { Input } from '../../ui/input';
import { LOOP_HELP } from '@/lib/flow/flowHelp';
import { Label } from '../../ui/label';
import { MoreOptions } from '../frame/MoreOptions';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../ui/select';
import { type ActionFormProps, BranchRows, Section, str } from './formKit';
import { ValueField } from './fields';

export function LoopForm({ nodeId, cfg, patch, f, Err, title }: ActionFormProps) {
  return (
    <Section title={title} hint={LOOP_HELP}>
      <ValueField
        field="items"
        f={f}
        Err={Err}
        nodeId={nodeId}
        label="List to go through"
        hintTestId="flow-hint-loop-items"
        accept="list"
        placeholder="Choose a list with + Use data"
        hint="A list from the trigger or an earlier step, like the items of an order. The steps on the 'For each item' path run once for every entry."
        value={cfg.items}
        onChange={(v) => patch({ items: v === '' ? undefined : v })}
      />
      <ValueField
        field="collect"
        f={f}
        Err={Err}
        nodeId={nodeId}
        label="Result to collect"
        hintTestId="flow-hint-loop-collect"
        accept="one"
        scope="loop-body"
        placeholder="Choose a step inside the loop"
        hint="After each item, this is added to a list. When the loop is done, the next step gets that whole list. Pick the result of a step inside the loop, or the current item."
        value={cfg.collect}
        onChange={(v) => patch({ collect: v === '' ? undefined : v })}
      />
      <MoreOptions defaultOpen={typeof cfg.max_iterations !== 'number' || !str(cfg.on_item_error)} testId="flow-more-options-loop">
        <div>
          <Label htmlFor="loop-max" size="sm">Most items to go through</Label>
          <Input
            id="loop-max"
            data-testid={f('max_iterations')}
            type="number"
            min={0}
            value={typeof cfg.max_iterations === 'number' ? cfg.max_iterations : ''}
            placeholder="10"
            onChange={(e) => patch({ max_iterations: e.target.value === '' ? undefined : parseInt(e.target.value, 10) })}
          />
          <FieldHint testId="flow-hint-loop-max">A safety limit. If the list is longer than this, the loop stops with a message instead of running.</FieldHint>
          <Err field="max_iterations" />
        </div>
        <div>
          <Label htmlFor="loop-on-error" size="sm">If one item fails</Label>
          <Select value={str(cfg.on_item_error)} onValueChange={(v) => patch({ on_item_error: v })}>
            <SelectTrigger id="loop-on-error" data-testid={f('on_item_error')}>
              <SelectValue placeholder="Choose..." />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="fail" description="The whole flow stops at the first item that fails." data-testid="flow-option-loop-on-error-fail">Stop the whole flow</SelectItem>
              <SelectItem value="skip" description="That item is left out and the rest carry on." data-testid="flow-option-loop-on-error-skip">Skip it and keep going</SelectItem>
            </SelectContent>
          </Select>
          <FieldHint testId="flow-hint-loop-on-error">Choose what happens when the steps inside the loop fail for one item.</FieldHint>
          <Err field="on_item_error" />
        </div>
      </MoreOptions>
      <BranchRows nodeId={nodeId} cfgType="foreach" cfg={cfg} />
      <Err field="branch.body" />
    </Section>
  );
}
