import { Examples, FieldHint, Code } from '../FieldHint';
import { CONDITION_EXAMPLES, conditionHelp } from '@/lib/flow/flowHelp';
import { MAX_EXPRESSION_LENGTH } from '@/lib/flow-condition/types';
import { PickerTextarea } from '../forms/formKit';

/**
 * "Write it yourself": the check as text, for people who want to. The help says what the text may contain, with examples.
 * The text is kept exactly as typed; nothing here rewrites it.
 */
export function RawExpression({ nodeId, value, onChange, testId, canEdit, handWritten }: {
  nodeId: string;
  value: string;
  onChange: (v: string) => void;
  testId: string;
  canEdit: boolean;
  /** Set when the text cannot be shown as rules: say so, once. */
  handWritten: boolean;
}) {
  return (
    <div className="space-y-2" data-testid="flow-condition-raw-area">
      {handWritten && (
        <p className="rounded-md bg-muted/50 px-2.5 py-2 text-xs" data-testid="flow-condition-handwritten">
          This was written by hand and can’t be shown as rules. It stays exactly as it is.
        </p>
      )}
      <PickerTextarea
        id="condition-expr"
        testId={testId}
        pickerTestId={`${testId}-picker`}
        nodeId={nodeId}
        label="Check (written by you)"
        value={value}
        onChange={onChange}
        format={(ref) => ref.replace(/\.(\w+)/g, "['$1']")}
        className="min-h-[120px]"
        mono
        placeholder="input['amount'] > 100"
      />
      {value.length > MAX_EXPRESSION_LENGTH && (
        <p role="alert" className="text-meta text-destructive" data-testid="flow-condition-raw-too-long">
          This is longer than {MAX_EXPRESSION_LENGTH} characters. Shorten it to save.
        </p>
      )}
      <FieldHint testId="flow-hint-condition">{conditionHelp(canEdit)}</FieldHint>
      <Examples testId="flow-condition-examples" title="Help and examples">
        <p>
          Data from the trigger is <Code>input['field']</Code>; a step before this one is <Code>step_name['field']</Code>. Text goes in quotes.
        </p>
        {CONDITION_EXAMPLES.map((ex) => (
          <p key={ex.text}>
            <Code>{ex.text}</Code> {ex.meaning}
          </p>
        ))}
      </Examples>
    </div>
  );
}
