import { CONDITION_EXAMPLES, conditionHelp } from '@/lib/flow/flowHelp';
import { Code, Examples, FieldHint } from '../FieldHint';
import { type ActionFormProps, BranchRows, PickerTextarea, Section, str } from './formKit';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';

export function ConditionForm({ nodeId, cfg, patch, f, Err, title }: ActionFormProps) {
  const { canManage } = useFlowPermissions();

  return (
    <Section title={title} hint="Checks a condition. The True path runs when it holds, otherwise the False path.">
      <div>
        <PickerTextarea
          id="condition-expr"
          testId={f('expression')}
          pickerTestId={`${f('expression')}-picker`}
          nodeId={nodeId}
          label="Condition"
          value={str(cfg.expression)}
          onChange={(v) => patch({ expression: v })}
          format={(ref) => ref.replace(/\.(\w+)/g, "['$1']")}
          className="min-h-[60px]"
          mono
          placeholder="input['amount'] > 100"
        />
        <FieldHint testId="flow-hint-condition">{conditionHelp(canManage)}</FieldHint>
        <Examples testId="flow-condition-examples" title="Show examples">
          {CONDITION_EXAMPLES.map((ex) => (
            <p key={ex.text}><Code>{ex.text}</Code> {ex.meaning}</p>
          ))}
        </Examples>
        <Err field="expression" />
      </div>
      <BranchRows nodeId={nodeId} cfgType="condition" cfg={cfg} />
      <Err field="branch.true" />
      <Err field="branch.false" />
    </Section>
  );
}
