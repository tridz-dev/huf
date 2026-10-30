import { useEffect, useMemo, useState } from 'react';
import { PencilLine } from 'lucide-react';
import { Button } from '../../ui/button';
import { ConditionBranches } from '../condition/ConditionBranches';
import { ConditionBuilder, ConditionSentence } from '../condition/ConditionBuilder';
import { useConditionSentence } from '../condition/conditionLabels';
import { RawExpression } from '../condition/RawExpression';
import { useDataCatalog } from '../data/useDataCatalog';
import { parseCondition } from '@/lib/flow-condition/parse';
import { type ActionFormProps, Section, str } from './formKit';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';

const PREF_KEY = 'huf.flow.condition.writeItYourself';

function readPref(): boolean {
  try {
    return window.localStorage.getItem(PREF_KEY) === '1';
  } catch {
    return false;
  }
}
function writePref(on: boolean): void {
  try {
    window.localStorage.setItem(PREF_KEY, on ? '1' : '0');
  } catch {
    /* a private window: the choice just is not remembered */
  }
}

/**
 * The Condition step: rules built from data, with a sentence saying what they mean, where each path goes, and an
 * opt-in "Write it yourself" box for the check as text. A check that cannot be shown as rules (written by hand, or
 * by an older version) opens in the text box and is never rewritten.
 */
export function ConditionForm({ nodeId, cfg, patch, f, Err, title }: ActionFormProps) {
  const { canManage } = useFlowPermissions();
  const expression = str(cfg.expression);
  const parseable = useMemo(() => parseCondition(expression) !== null, [expression]);
  const [raw, setRaw] = useState(() => !parseable || readPref());
  const { model } = useDataCatalog(nodeId);
  const sentence = useConditionSentence(expression, model);

  // The text became something rules cannot show (undo to a hand-written check): stay with the text.
  useEffect(() => {
    if (!parseable && !raw) setRaw(true);
  }, [parseable, raw]);

  const canSwitchBack = parseable; // empty or in the shapes the builder reads
  const choose = (next: boolean) => {
    setRaw(next);
    writePref(next);
  };

  return (
    <Section title={title} hint="Checks a condition. The Yes path runs when it holds, otherwise the No path.">
      {!canManage ? (
        <div className="space-y-2" data-testid="flow-condition-readonly">
          {parseable ? (
            <ConditionSentence sentence={sentence} empty />
          ) : (
            <p className="rounded-md bg-muted/50 px-2.5 py-2 text-xs" data-testid="flow-condition-handwritten">
              This check was written by hand and can’t be shown as rules.
            </p>
          )}
        </div>
      ) : (
        <div className="space-y-2">
          {raw ? (
            <RawExpression nodeId={nodeId} value={expression} onChange={(v) => patch({ expression: v })} testId={f('expression')} canEdit={canManage} handWritten={!parseable} />
          ) : (
            <ConditionBuilder nodeId={nodeId} expression={expression} onChange={(v) => patch({ expression: v })} />
          )}
          <Err field="expression" />
          {canSwitchBack || !raw ? (
            <Button type="button" variant="ghost" size="sm" className="-ml-2 text-muted-foreground" onClick={() => choose(!raw)} data-testid="flow-condition-raw-toggle" aria-pressed={raw}>
              <PencilLine className="mr-1 h-3.5 w-3.5" />
              {raw ? 'Back to rules' : 'Write it yourself'}
            </Button>
          ) : (
            <p className="text-meta text-muted-foreground" data-testid="flow-condition-raw-locked">
              To use rules instead, clear the text above.
            </p>
          )}
        </div>
      )}
      <ConditionBranches nodeId={nodeId} cfg={cfg} />
      <Err field="branch.true" />
      <Err field="branch.false" />
    </Section>
  );
}
