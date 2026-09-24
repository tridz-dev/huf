import { useState, useCallback, useEffect, type ReactNode } from 'react';
import { HelperText } from '@/components/ui/helper-text';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Plus, Trash2, AlertCircle } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { validatePolicyDefinition } from '@/services/decisionApi';
import { cn } from '@/lib/utils';

type QuestionKind = 'select' | 'judge' | 'score';

interface Option {
  id: string;
  description: string;
}

interface Question {
  id: string;
  kind: QuestionKind;
  instructions: string;
  options: Option[];
  allow_none?: boolean;
  positive_criteria?: string;
  negative_criteria?: string;
}

interface StateBinding {
  name: string;
  path: string;
}

export interface PolicyDefinition {
  policy_id: string;
  questions: Question[];
  version?: string;
  minimum_confidence?: number;
  fallback_action?: string;
  store_state?: boolean;
  max_state_bytes?: number;
  required_modalities?: string[];
  state_bindings: StateBinding[];
}

/**
 * `fallback_action` is the label the runtime records on a call (`policy_fallback_action`)
 * once every deployment has failed -- it is the policy's answer to "if the model fails".
 * It is NOT consulted for low confidence: a below-threshold answer always gates to
 * `uncertain` (huf/ai/decision/gating.py), so there is no separate low-confidence action.
 */
export const FALLBACK_ACTIONS: { value: string; label: string }[] = [
  { value: 'fail_closed', label: 'Fail closed' },
  { value: 'uncertain', label: 'Return uncertain' },
  { value: 'review', label: 'Flag for review' },
];

export const DEFAULT_FALLBACK_ACTION = 'fail_closed';

function uniqueQuestionId(questions: Question[]): string {
  const taken = new Set(questions.map((q) => q.id));
  let n = questions.length + 1;
  while (taken.has(`question_${n}`)) n += 1;
  return `question_${n}`;
}

function newQuestion(existing: Question[]): Question {
  return {
    id: uniqueQuestionId(existing),
    kind: 'judge',
    instructions: '',
    options: [],
    positive_criteria: '',
    negative_criteria: '',
  };
}

/**
 * Starting definition for a new policy or ad-hoc run. Every behaviour field that has a
 * meaningful default is set explicitly, so what the form shows is what gets submitted.
 *
 * `minimum_confidence` is deliberately left unset (gate off): setting it makes the runtime
 * reject any deployment without `supports_confidence` (DECISION_UNSUPPORTED_CAPABILITY,
 * runtime._validate_capabilities), and that flag defaults to off on Decision Deployment.
 * The field renders "Off" for this state rather than an ambiguous blank.
 */
export function newPolicyDefinition(policyId: string): PolicyDefinition {
  return {
    policy_id: policyId,
    questions: [{ ...newQuestion([]), instructions: 'Describe what this question should decide.' }],
    state_bindings: [{ name: 'request', path: 'request' }],
    fallback_action: DEFAULT_FALLBACK_ACTION,
    store_state: false,
  };
}

interface QuestionBuilderProps {
  value: PolicyDefinition;
  onChange: (value: PolicyDefinition) => void;
  readOnly?: boolean;
}

/** Compact field label: small text with the explanation as a native tooltip. */
function FieldLabel({ children, hint, className }: { children: ReactNode; hint?: string; className?: string }) {
  return (
    <label
      className={cn(
        'mb-1 block text-xs font-medium text-steel',
        hint && 'cursor-help underline decoration-dotted decoration-line underline-offset-2',
        className,
      )}
      title={hint}
    >
      {children}
    </label>
  );
}

function SectionHeader({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-2">
      {/* Plain concatenation, not cn(): tailwind-merge drops the custom text-eyebrow size. */}
      <span
        className={`font-mono text-eyebrow font-medium uppercase text-steel${hint ? ' cursor-help underline decoration-dotted decoration-line underline-offset-2' : ''}`}
        title={hint}
      >
        {title}
      </span>
      {action}
    </div>
  );
}

const compactTextarea = 'min-h-0 resize-y px-2.5 py-1.5 text-xs';

export function QuestionBuilder({
  value,
  onChange,
  readOnly = false,
}: QuestionBuilderProps) {
  const [jsonText, setJsonText] = useState(JSON.stringify(value, null, 2));
  const [validationError, setValidationError] = useState<string | null>(null);
  const [isValidating, setIsValidating] = useState(false);

  // Debounce validation
  useEffect(() => {
    const timer = setTimeout(async () => {
      if (jsonText) {
        setIsValidating(true);
        try {
          const parsed = JSON.parse(jsonText);
          const result = await validatePolicyDefinition(parsed);
          if (!result.valid) {
            setValidationError(result.message || 'Invalid policy definition');
          } else {
            setValidationError(null);
          }
        } catch (err) {
          if (err instanceof SyntaxError) {
            setValidationError('Invalid JSON');
          } else {
            setValidationError('Validation error');
          }
        } finally {
          setIsValidating(false);
        }
      }
    }, 500);

    return () => clearTimeout(timer);
  }, [jsonText]);

  const handleJsonChange = useCallback((text: string) => {
    setJsonText(text);
    try {
      const parsed = JSON.parse(text);
      onChange(parsed as PolicyDefinition);
      setValidationError(null);
    } catch {
      // Don't update on invalid JSON until it's fixed
    }
  }, [onChange]);

  /** Every builder edit goes through here so the Raw JSON tab stays in sync. */
  const commit = useCallback(
    (updated: PolicyDefinition) => {
      onChange(updated);
      setJsonText(JSON.stringify(updated, null, 2));
    },
    [onChange]
  );

  const handleQuestionChange = useCallback(
    (index: number, updatedQuestion: Question) => {
      const newQuestions = [...value.questions];
      newQuestions[index] = updatedQuestion;
      commit({ ...value, questions: newQuestions });
    },
    [value, commit]
  );

  const handleAddQuestion = useCallback(() => {
    commit({ ...value, questions: [...value.questions, newQuestion(value.questions)] });
  }, [value, commit]);

  const handleRemoveQuestion = useCallback(
    (index: number) => {
      commit({ ...value, questions: value.questions.filter((_, i) => i !== index) });
    },
    [value, commit]
  );

  const handleAddStateBinding = useCallback(() => {
    commit({ ...value, state_bindings: [...(value.state_bindings || []), { name: '', path: '' }] });
  }, [value, commit]);

  const handleUpdateStateBinding = useCallback(
    (index: number, updatedBinding: StateBinding) => {
      const bindings = [...(value.state_bindings || [])];
      bindings[index] = updatedBinding;
      commit({ ...value, state_bindings: bindings });
    },
    [value, commit]
  );

  const handleRemoveStateBinding = useCallback(
    (index: number) => {
      commit({ ...value, state_bindings: (value.state_bindings || []).filter((_, i) => i !== index) });
    },
    [value, commit]
  );

  if (readOnly) {
    return (
      <div className="rounded border border-line p-3">
        <pre className="overflow-auto font-mono text-xs">{JSON.stringify(value, null, 2)}</pre>
      </div>
    );
  }

  const bindings = value.state_bindings || [];

  return (
    <Tabs defaultValue="builder" className="w-full">
      <TabsList variant="pill" size="compact" className="mb-3">
        <TabsTrigger value="builder" size="compact">Builder</TabsTrigger>
        <TabsTrigger value="json" size="compact">Raw JSON</TabsTrigger>
      </TabsList>

      <TabsContent value="builder" className="mt-0 space-y-4">
        {/* Questions */}
        <div className="space-y-2">
          <SectionHeader
            title={`Questions · ${value.questions.length}`}
            hint="Select picks one option, Judge answers yes/no, Score rates on a scale. The model answers every question in one call."
            action={
              <Button type="button" variant="ghost" size="sm" onClick={handleAddQuestion} className="gap-1">
                <Plus className="h-3.5 w-3.5" />
                Add question
              </Button>
            }
          />

          {value.questions.length === 0 ? (
            <Alert>
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>At least one question is required.</AlertDescription>
            </Alert>
          ) : (
            <div className="space-y-2">
              {value.questions.map((question, index) => (
                <QuestionCard
                  key={index}
                  question={question}
                  onUpdate={(updated) => handleQuestionChange(index, updated)}
                  onRemove={() => handleRemoveQuestion(index)}
                />
              ))}
            </div>
          )}
        </div>

        {/* Behavior */}
        <div className="space-y-2 border-t border-line pt-3">
          <SectionHeader title="Behavior" />
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
            <div>
              <FieldLabel hint="0-1. Below this, the call gates to 'uncertain'. Off = no gate. Needs a deployment with Supports Confidence on, or the run fails with an unsupported-capability error.">
                Min confidence
              </FieldLabel>
              <Input
                size="sm"
                type="number"
                min="0"
                max="1"
                step="0.05"
                placeholder="Off"
                value={value.minimum_confidence ?? ''}
                onChange={(e) => {
                  const val = e.target.value ? parseFloat(e.target.value) : undefined;
                  commit({ ...value, minimum_confidence: val });
                }}
              />
            </div>

            <div>
              <FieldLabel hint="Recorded on the call as the fallback action once every deployment in the failover chain has failed.">
                If the model fails
              </FieldLabel>
              <Select
                value={value.fallback_action || undefined}
                onValueChange={(val) => commit({ ...value, fallback_action: val })}
              >
                <SelectTrigger size="sm">
                  <SelectValue placeholder="Not set" />
                </SelectTrigger>
                <SelectContent>
                  {FALLBACK_ACTIONS.map((a) => (
                    <SelectItem key={a.value} value={a.value}>
                      {a.label}
                    </SelectItem>
                  ))}
                  {value.fallback_action &&
                    !FALLBACK_ACTIONS.some((a) => a.value === value.fallback_action) && (
                      <SelectItem value={value.fallback_action}>{value.fallback_action}</SelectItem>
                    )}
                </SelectContent>
              </Select>
            </div>

            <label
              className="flex h-control-sm cursor-pointer items-center gap-2 text-xs text-ink"
              title="Keep the provider-visible state on the Decision Call record. Off by default."
            >
              <Checkbox
                checked={Boolean(value.store_state)}
                onCheckedChange={(checked) => commit({ ...value, store_state: checked === true })}
              />
              Store state
            </label>
          </div>
        </div>

        {/* State bindings */}
        <div className="space-y-2 border-t border-line pt-3">
          <SectionHeader
            title="State bindings"
            hint="Which fields of the state are sent to the model: a name the model sees, and the JSON path it is read from."
            action={
              <Button type="button" variant="ghost" size="sm" onClick={handleAddStateBinding} className="gap-1">
                <Plus className="h-3.5 w-3.5" />
                Add binding
              </Button>
            }
          />

          {bindings.length === 0 ? (
            <HelperText tone="destructive">At least one state binding is required.</HelperText>
          ) : (
            <div className="space-y-1.5">
              <div className="grid grid-cols-[1fr_1fr_28px] gap-2 text-xs text-steel-soft">
                <span>Name</span>
                <span>Path</span>
                <span />
              </div>
              {bindings.map((binding, index) => (
                <div key={index} className="grid grid-cols-[1fr_1fr_28px] items-center gap-2">
                  <Input
                    size="sm"
                    placeholder="request"
                    aria-label="Binding name"
                    value={binding.name}
                    onChange={(e) => handleUpdateStateBinding(index, { ...binding, name: e.target.value })}
                  />
                  <Input
                    size="sm"
                    placeholder="input.request"
                    aria-label="JSON path"
                    className="font-mono"
                    value={binding.path}
                    onChange={(e) => handleUpdateStateBinding(index, { ...binding, path: e.target.value })}
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => handleRemoveStateBinding(index)}
                    aria-label="Remove binding"
                    className="text-steel hover:text-destructive"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>
      </TabsContent>

      <TabsContent value="json" className="mt-0 space-y-2">
        {validationError && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{validationError}</AlertDescription>
          </Alert>
        )}
        <Textarea
          value={jsonText}
          onChange={(e) => handleJsonChange(e.target.value)}
          className="font-mono text-xs"
          rows={18}
          disabled={isValidating}
        />
        <HelperText>
          {isValidating ? 'Validating…' : 'Edits here update the builder as you type.'}
        </HelperText>
      </TabsContent>
    </Tabs>
  );
}

interface QuestionCardProps {
  question: Question;
  onUpdate: (updated: Question) => void;
  onRemove: () => void;
}

const KIND_HINT =
  'Select: choose one of the options. Judge: binary yes/no. Score: pick a level on the scale defined by the options.';

function QuestionCard({ question, onUpdate, onRemove }: QuestionCardProps) {
  return (
    <div className="space-y-2 rounded border border-line bg-panel p-2.5">
      {/* Type · ID · remove */}
      <div className="grid grid-cols-[minmax(0,9rem)_minmax(0,1fr)_28px] items-end gap-2">
        <div>
          <FieldLabel hint={KIND_HINT}>Type</FieldLabel>
          <Select
            value={question.kind}
            onValueChange={(val) =>
              onUpdate({
                ...question,
                kind: val as QuestionKind,
                options:
                  val === 'judge'
                    ? []
                    : question.options.length === 0
                    ? [
                        { id: 'option1', description: '' },
                        { id: 'option2', description: '' },
                      ]
                    : question.options,
              })
            }
          >
            <SelectTrigger size="sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="select">Select</SelectItem>
              <SelectItem value="judge">Judge (yes/no)</SelectItem>
              <SelectItem value="score">Score</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div>
          <FieldLabel hint="Unique within the policy; answers are keyed by it.">ID</FieldLabel>
          <Input
            size="sm"
            className="font-mono"
            value={question.id}
            onChange={(e) => onUpdate({ ...question, id: e.target.value })}
          />
        </div>

        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          onClick={onRemove}
          aria-label="Remove question"
          title="Remove question"
          className="text-steel hover:text-destructive"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </div>

      <div>
        <FieldLabel>Instructions</FieldLabel>
        <Textarea
          value={question.instructions}
          onChange={(e) => onUpdate({ ...question, instructions: e.target.value })}
          className={compactTextarea}
          rows={2}
          placeholder="What should the model decide?"
        />
      </div>

      {question.kind === 'judge' && (
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <div>
            <FieldLabel hint="What must be true for a yes answer.">Yes when</FieldLabel>
            <Textarea
              value={question.positive_criteria || ''}
              onChange={(e) => onUpdate({ ...question, positive_criteria: e.target.value })}
              className={compactTextarea}
              rows={2}
              placeholder="What makes this true?"
            />
          </div>
          <div>
            <FieldLabel hint="What makes a no answer correct.">No when</FieldLabel>
            <Textarea
              value={question.negative_criteria || ''}
              onChange={(e) => onUpdate({ ...question, negative_criteria: e.target.value })}
              className={compactTextarea}
              rows={2}
              placeholder="What makes this false?"
            />
          </div>
        </div>
      )}

      {(question.kind === 'select' || question.kind === 'score') && (
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <FieldLabel className="mb-0">
              {question.kind === 'score' ? 'Scale levels' : 'Options'} · {question.options.length}
            </FieldLabel>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="gap-1"
              onClick={() =>
                onUpdate({
                  ...question,
                  options: [
                    ...question.options,
                    { id: `option${question.options.length + 1}`, description: '' },
                  ],
                })
              }
            >
              <Plus className="h-3.5 w-3.5" />
              Add
            </Button>
          </div>

          {question.options.map((option, optIndex) => (
            <div key={optIndex} className="grid grid-cols-[minmax(0,9rem)_minmax(0,1fr)_28px] items-center gap-2">
              <Input
                size="sm"
                placeholder="Option ID"
                aria-label="Option ID"
                className="font-mono"
                value={option.id}
                onChange={(e) => {
                  const updated = [...question.options];
                  updated[optIndex] = { ...option, id: e.target.value };
                  onUpdate({ ...question, options: updated });
                }}
              />
              <Input
                size="sm"
                placeholder="Description"
                aria-label="Option description"
                value={option.description}
                onChange={(e) => {
                  const updated = [...question.options];
                  updated[optIndex] = { ...option, description: e.target.value };
                  onUpdate({ ...question, options: updated });
                }}
              />
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label="Remove option"
                className="text-steel hover:text-destructive"
                onClick={() =>
                  onUpdate({ ...question, options: question.options.filter((_, i) => i !== optIndex) })
                }
                disabled={question.options.length <= 1}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
