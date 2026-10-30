import { useCallback, useEffect, useRef, useState } from 'react';
import { Plus } from 'lucide-react';
import { Button } from '../../ui/button';
import { useDataCatalog } from '../data/useDataCatalog';
import { compileCondition, isCompleteRule } from '@/lib/flow-condition/compile';
import { parseCondition } from '@/lib/flow-condition/parse';
import { emptyRule, newRuleId } from '@/lib/flow-condition/operators';
import { MAX_EXPRESSION_LENGTH, type ConditionModel, type Group, type Match, type Rule } from '@/lib/flow-condition/types';
import { cn } from '@/lib/utils';
import { RuleRow } from './RuleRow';
import { useConditionSentence } from './conditionLabels';

const withIds = (m: ConditionModel): ConditionModel => ({
  ...m,
  items: m.items.map((i) => (i.type === 'group' ? { ...i, id: newRuleId(), items: i.items.map((r) => ({ ...r, id: newRuleId() })) } : { ...i, id: newRuleId() })),
});

function MatchToggle({ value, onChange, testId, label, disabled }: { value: Match; onChange: (m: Match) => void; testId: string; label: string; disabled?: boolean }) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-md border border-border p-0.5" data-testid={testId}>
      {(['all', 'any'] as const).map((m) => (
        <button
          key={m}
          type="button"
          role="radio"
          aria-checked={value === m}
          disabled={disabled}
          data-testid={`${testId}-${m}`}
          onClick={() => onChange(m)}
          className={cn(
            'rounded px-2.5 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal',
            value === m ? 'bg-signal-tint text-signal-ink' : 'text-muted-foreground hover:text-foreground'
          )}
        >
          {m === 'all' ? 'All of' : 'Any of'}
        </button>
      ))}
    </div>
  );
}

interface BuilderProps {
  nodeId: string;
  expression: string;
  onChange: (expression: string) => void;
  disabled?: boolean;
}

/**
 * The rule builder: rows of "data / how / value", an All of / Any of choice, groups one level deep, and the sentence it
 * means. It keeps its own unfinished rows; only complete rules reach the step as the expression text.
 */
export function ConditionBuilder({ nodeId, expression, onChange, disabled }: BuilderProps) {
  const { model: picker, loading, refresh } = useDataCatalog(nodeId);
  const [state, setState] = useState<ConditionModel>(() => withIds(parseCondition(expression) ?? { match: 'all', items: [] }));
  const sent = useRef(expression);

  // Text changed from outside (undo, redo, another editor of the same step): read it again.
  useEffect(() => {
    if (expression === sent.current) return;
    sent.current = expression;
    const parsed = parseCondition(expression);
    if (parsed) setState(withIds(parsed));
  }, [expression]);

  const commit = useCallback(
    (next: ConditionModel) => {
      setState(next);
      const text = compileCondition(next);
      if (text !== sent.current) {
        sent.current = text;
        onChange(text);
      }
    },
    [onChange]
  );

  const sentence = useConditionSentence(compileCondition(state), picker);
  const tooLong = compileCondition(state).length > MAX_EXPRESSION_LENGTH;
  const ruleCount = state.items.reduce((n, i) => n + (i.type === 'group' ? i.items.length : 1), 0);
  const itemCount = state.items.length;

  const patchItem = (index: number, next: Rule | Group) => commit({ ...state, items: state.items.map((it, i) => (i === index ? next : it)) });
  const removeItem = (index: number) => commit({ ...state, items: state.items.filter((_, i) => i !== index) });
  const rowProps = { model: picker, loading, refresh, disabled };

  return (
    <div className="space-y-3" data-testid="flow-condition-builder">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-medium text-foreground">Yes when</span>
        <MatchToggle value={state.match} onChange={(match) => commit({ ...state, match })} testId="flow-condition-match" label="Which rules must be true" disabled={disabled} />
        <span className="text-xs text-muted-foreground">these rules are true</span>
      </div>

      <div className="space-y-2">
        {state.items.map((item, index) =>
          item.type === 'group' ? (
            <div key={item.id} className="space-y-2 rounded-md border border-dashed border-border bg-muted/30 p-2" data-testid={`flow-condition-group-${index}`} role="group" aria-label={`Group ${index + 1}`}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <MatchToggle value={item.match} onChange={(match) => patchItem(index, { ...item, match })} testId={`flow-condition-group-${index}-match`} label={`Which rules in group ${index + 1} must be true`} disabled={disabled} />
                {!disabled && (
                  <Button type="button" variant="ghost" size="sm" onClick={() => removeItem(index)} data-testid={`flow-condition-group-${index}-remove`} aria-label={`Remove group ${index + 1}`}>
                    Remove group
                  </Button>
                )}
              </div>
              {item.items.map((rule, ri) => (
                <RuleRow
                  key={rule.id}
                  {...rowProps}
                  rule={rule}
                  testId={`flow-condition-group-${index}-row-${ri}`}
                  name={`Rule ${ri + 1} in group ${index + 1}`}
                  onChange={(next) => patchItem(index, { ...item, items: item.items.map((r, i) => (i === ri ? next : r)) })}
                  onRemove={() => patchItem(index, { ...item, items: item.items.filter((_, i) => i !== ri) })}
                />
              ))}
              {!disabled && (
                <Button type="button" variant="outline" size="sm" onClick={() => patchItem(index, { ...item, items: [...item.items, emptyRule()] })} data-testid={`flow-condition-group-${index}-add-rule`}>
                  <Plus className="mr-1 h-3.5 w-3.5" />
                  Add rule
                </Button>
              )}
            </div>
          ) : (
            <RuleRow
              key={item.id}
              {...rowProps}
              rule={item}
              testId={`flow-condition-row-${index}`}
              name={`Rule ${index + 1}`}
              onChange={(next) => patchItem(index, next)}
              onRemove={() => removeItem(index)}
            />
          )
        )}
      </div>

      {!disabled && (
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" size="sm" onClick={() => commit({ ...state, items: [...state.items, emptyRule()] })} data-testid="flow-condition-add-rule">
            <Plus className="mr-1 h-3.5 w-3.5" />
            Add rule
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={() => commit({ ...state, items: [...state.items, { type: 'group', id: newRuleId(), match: 'any', items: [emptyRule()] }] })} data-testid="flow-condition-add-group">
            <Plus className="mr-1 h-3.5 w-3.5" />
            Add group
          </Button>
        </div>
      )}

      {tooLong ? (
        <p role="alert" className="text-meta text-destructive" data-testid="flow-condition-too-long">
          There are too many rules to save. Remove a few, or use shorter values.
        </p>
      ) : null}

      <ConditionSentence sentence={sentence} unfinished={state.items.some((i) => (i.type === 'group' ? i.items.some((r) => !isCompleteRule(r)) : !isCompleteRule(i)))} empty={ruleCount === 0 || itemCount === 0} />
    </div>
  );
}

/** "Yes when Amount is more than 100 and Status is Paid", in a quiet box under the rules. */
export function ConditionSentence({ sentence, unfinished, empty }: { sentence: string | null; unfinished?: boolean; empty?: boolean }) {
  return (
    <div className="rounded-md bg-muted/50 px-2.5 py-2 text-xs" data-testid="flow-condition-sentence" aria-live="polite">
      {sentence ? (
        <>
          <span className="font-medium">Yes when </span>
          <span data-testid="flow-condition-sentence-text">{sentence}</span>
          <span className="font-medium">.</span> <span className="text-muted-foreground">Otherwise the flow follows No.</span>
        </>
      ) : (
        <span className="text-muted-foreground" data-testid="flow-condition-sentence-empty">
          {empty ? 'Add a rule to say when the flow follows Yes.' : 'Finish the rule above to say when the flow follows Yes.'}
        </span>
      )}
      {sentence && unfinished ? <p className="mt-1 text-muted-foreground">A rule that is not finished is left out until you finish it.</p> : null}
    </div>
  );
}
