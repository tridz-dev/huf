import { FieldHint } from '../FieldHint';
import { Input } from '../../ui/input';
import { LOOP_HELP } from '@/lib/flow/flowHelp';
import { Label } from '../../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../ui/select';
import { VariablePicker } from '../../ui/VariablePicker';
import { type ActionFormProps, asObj, BranchRows, Section, str } from './formKit';

export function LoopForm({ nodeId, cfg, patch, f, Err, title }: ActionFormProps) {

  const itemsRef = str(asObj(cfg.items).$from);
  const collectRef = str(asObj(cfg.collect).$from);
  return (
    <Section title={title} hint={LOOP_HELP}>
      <div>
        <div className="flex justify-between items-center mb-1">
          <Label htmlFor="loop-items" size="sm">List to loop over</Label>
          <VariablePicker currentNodeId={nodeId} testId="flow-loop-items-picker" accept="list" onSelect={(ref) => patch({ items: { $from: ref } })} />
        </div>
        <Input id="loop-items" data-testid={f('items')} className="font-mono text-xs" value={itemsRef} onChange={(e) => patch({ items: { $from: e.target.value } })} placeholder="input.recipients" />
        <FieldHint testId="flow-hint-loop-items">A list from the trigger or an earlier step, for example input.recipients. Click + Use data to pick it.</FieldHint>
        <Err field="items" />
      </div>
      <div>
        <Label htmlFor="loop-max" size="sm">Maximum items to process</Label>
        <Input
          id="loop-max"
          data-testid={f('max_iterations')}
          type="number"
          min={0}
          value={typeof cfg.max_iterations === 'number' ? cfg.max_iterations : ''}
          onChange={(e) => patch({ max_iterations: e.target.value === '' ? undefined : parseInt(e.target.value, 10) })}
        />
        <FieldHint testId="flow-hint-loop-max">Safety limit. If the list has more items than this, the loop fails instead of running.</FieldHint>
        <Err field="max_iterations" />
      </div>
      <div>
        <Label htmlFor="loop-on-error" size="sm">If one item fails</Label>
        <Select value={str(cfg.on_item_error)} onValueChange={(v) => patch({ on_item_error: v })}>
          <SelectTrigger id="loop-on-error" data-testid={f('on_item_error')}>
            <SelectValue placeholder="Choose..." />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="fail" data-testid="flow-option-loop-on-error-fail">Stop the flow</SelectItem>
            <SelectItem value="skip" data-testid="flow-option-loop-on-error-skip">Skip that item</SelectItem>
          </SelectContent>
        </Select>
        <FieldHint testId="flow-hint-loop-on-error">Stop the flow ends the run at the first failing item. Skip that item carries on with the rest.</FieldHint>
        <Err field="on_item_error" />
      </div>
      <div>
        <div className="flex justify-between items-center mb-1">
          <Label htmlFor="loop-collect" size="sm">Result to collect from each item</Label>
          <VariablePicker currentNodeId={nodeId} scope="loop-body" testId="flow-loop-collect-picker" onSelect={(ref) => patch({ collect: { $from: ref } })} />
        </div>
        <Input id="loop-collect" data-testid={f('collect')} className="font-mono text-xs" value={collectRef} onChange={(e) => patch({ collect: { $from: e.target.value } })} placeholder="node_1234.value" />
        <FieldHint testId="flow-hint-loop-collect">After each item, this value is added to a list. When the loop is done, the next step receives that list. Pick a step inside the loop with Use data.</FieldHint>
        <Err field="collect" />
      </div>
      <BranchRows nodeId={nodeId} cfgType="foreach" cfg={cfg} />
      <Err field="branch.body" />
    </Section>
  );
}
