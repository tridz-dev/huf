import { useState, useCallback, useEffect } from 'react';
import { HelperText } from '@/components/ui/helper-text';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
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

interface QuestionBuilderProps {
  value: PolicyDefinition;
  onChange: (value: PolicyDefinition) => void;
  readOnly?: boolean;
}

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

  const handleQuestionChange = useCallback(
    (index: number, updatedQuestion: Question) => {
      const newQuestions = [...value.questions];
      newQuestions[index] = updatedQuestion;
      const updated = { ...value, questions: newQuestions };
      onChange(updated);
      setJsonText(JSON.stringify(updated, null, 2));
    },
    [value, onChange]
  );

  const handleAddQuestion = useCallback(() => {
    const newQuestion: Question = {
      id: `q${value.questions.length + 1}`,
      kind: 'select',
      instructions: '',
      options: [
        { id: 'option1', description: '' },
        { id: 'option2', description: '' },
      ],
      allow_none: false,
      positive_criteria: '',
      negative_criteria: '',
    };
    const updated = {
      ...value,
      questions: [...value.questions, newQuestion],
    };
    onChange(updated);
    setJsonText(JSON.stringify(updated, null, 2));
  }, [value, onChange]);

  const handleRemoveQuestion = useCallback(
    (index: number) => {
      const updated = {
        ...value,
        questions: value.questions.filter((_, i) => i !== index),
      };
      onChange(updated);
      setJsonText(JSON.stringify(updated, null, 2));
    },
    [value, onChange]
  );

  const handleAddStateBinding = useCallback(() => {
    const newBinding: StateBinding = { name: '', path: '' };
    const updated = {
      ...value,
      state_bindings: [...(value.state_bindings || []), newBinding],
    };
    onChange(updated);
    setJsonText(JSON.stringify(updated, null, 2));
  }, [value, onChange]);

  const handleUpdateStateBinding = useCallback(
    (index: number, updatedBinding: StateBinding) => {
      const updated = {
        ...value,
        state_bindings: [
          ...(value.state_bindings || []).slice(0, index),
          updatedBinding,
          ...(value.state_bindings || []).slice(index + 1),
        ],
      };
      onChange(updated);
      setJsonText(JSON.stringify(updated, null, 2));
    },
    [value, onChange]
  );

  const handleRemoveStateBinding = useCallback(
    (index: number) => {
      const updated = {
        ...value,
        state_bindings: (value.state_bindings || []).filter((_, i) => i !== index),
      };
      onChange(updated);
      setJsonText(JSON.stringify(updated, null, 2));
    },
    [value, onChange]
  );

  if (readOnly) {
    return (
      <div className="space-y-6">
        <div className="rounded-lg border p-4">
          <pre className="overflow-auto text-sm">
            {JSON.stringify(value, null, 2)}
          </pre>
        </div>
      </div>
    );
  }

  return (
    <Tabs defaultValue="builder" className="w-full">
      <TabsList className="grid w-full grid-cols-2">
        <TabsTrigger value="builder">Builder</TabsTrigger>
        <TabsTrigger value="json">Raw JSON</TabsTrigger>
      </TabsList>

      <TabsContent value="builder" className="space-y-6">
        {/* Questions Section */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold">Questions</h3>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleAddQuestion}
              disabled={readOnly}
            >
              <Plus className="mr-2 h-4 w-4" />
              Add question
            </Button>
          </div>
          <HelperText>
            Add select (pick one option), judge (yes/no decision), or score (rate on a scale)
            questions. The model will answer each.
          </HelperText>

          {value.questions.length === 0 ? (
            <Alert>
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>
                At least one question is required. Click "Add question" to start.
              </AlertDescription>
            </Alert>
          ) : (
            <div className="space-y-4">
              {value.questions.map((question, index) => (
                <QuestionCard
                  key={index}
                  question={question}
                  onUpdate={(updated) => handleQuestionChange(index, updated)}
                  onRemove={() => handleRemoveQuestion(index)}
                  readOnly={readOnly}
                />
              ))}
            </div>
          )}
        </div>

        {/* Confidence and Fallback Section */}
        <div className="space-y-4 border-t pt-6">
          <h3 className="font-semibold">Behavior</h3>

          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <label className="text-sm font-medium">Minimum confidence</label>
              <Input
                type="number"
                min="0"
                max="1"
                step="0.01"
                value={value.minimum_confidence ?? ''}
                onChange={(e) => {
                  const val = e.target.value ? parseFloat(e.target.value) : undefined;
                  onChange({ ...value, minimum_confidence: val });
                }}
                disabled={readOnly}
                className="mt-2"
              />
              <HelperText className="mt-2">
                If the model's confidence falls below this threshold, apply the low-confidence
                action (0-1 scale).
              </HelperText>
            </div>

            <div>
              <label className="text-sm font-medium">Low confidence action</label>
              <Select
                value={value.fallback_action || 'uncertain'}
                onValueChange={(val) =>
                  onChange({ ...value, fallback_action: val })
                }
                disabled={readOnly}
              >
                <SelectTrigger className="mt-2">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="uncertain">Treat as uncertain</SelectItem>
                  <SelectItem value="fallback">Use fallback</SelectItem>
                  <SelectItem value="review">Request review</SelectItem>
                </SelectContent>
              </Select>
              <HelperText className="mt-2">
                What to do when low confidence is detected.
              </HelperText>
            </div>
          </div>

          <div>
            <label className="text-sm font-medium">If the model fails</label>
            <Select
              value={value.store_state ? 'store' : 'fail_closed'}
              onValueChange={(val) => {
                // This will be expanded in future versions
                onChange({ ...value, store_state: val === 'store' });
              }}
              disabled={readOnly}
            >
              <SelectTrigger className="mt-2">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="fail_closed">Fail closed</SelectItem>
                <SelectItem value="fallback">Use fallback</SelectItem>
                <SelectItem value="review">Request review</SelectItem>
              </SelectContent>
            </Select>
            <HelperText className="mt-2">
              The policy's failure action determines what happens when the model errors.
            </HelperText>
          </div>
        </div>

        {/* State Bindings Section */}
        <div className="space-y-4 border-t pt-6">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-semibold">State bindings</h3>
              <HelperText className="mt-1">
                Declare which fields from your state will be sent to the model.
              </HelperText>
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleAddStateBinding}
              disabled={readOnly}
            >
              <Plus className="mr-2 h-4 w-4" />
              Add binding
            </Button>
          </div>

          {(!value.state_bindings || value.state_bindings.length === 0) && (
            <Alert>
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>
                At least one state binding is required to specify what data the policy needs.
              </AlertDescription>
            </Alert>
          )}

          <div className="space-y-3">
            {(value.state_bindings || []).map((binding, index) => (
              <div key={index} className="flex gap-2">
                <div className="flex-1 space-y-2">
                  <Input
                    placeholder="Binding name (e.g., 'request')"
                    value={binding.name}
                    onChange={(e) =>
                      handleUpdateStateBinding(index, {
                        ...binding,
                        name: e.target.value,
                      })
                    }
                    disabled={readOnly}
                  />
                  <Input
                    placeholder="JSON path (e.g., 'input.request')"
                    value={binding.path}
                    onChange={(e) =>
                      handleUpdateStateBinding(index, {
                        ...binding,
                        path: e.target.value,
                      })
                    }
                    disabled={readOnly}
                  />
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => handleRemoveStateBinding(index)}
                  disabled={readOnly}
                  className="self-start mt-2"
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            ))}
          </div>
        </div>

        {/* API Access */}
        <div className="space-y-4 border-t pt-6">
          <div>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={false} // Placeholder for future use
                onChange={() => {
                  // Will be implemented in future versions
                }}
                disabled={readOnly}
              />
              <span className="text-sm font-medium">Allow external API calls</span>
            </label>
            <HelperText className="mt-2 ml-6">
              When enabled, this policy can be called via the public Decision API.
            </HelperText>
          </div>
        </div>
      </TabsContent>

      <TabsContent value="json" className="space-y-4">
        <HelperText>
          Edit the policy definition as JSON. The builder above updates as you type.
        </HelperText>
        {validationError && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{validationError}</AlertDescription>
          </Alert>
        )}
        <Textarea
          value={jsonText}
          onChange={(e) => handleJsonChange(e.target.value)}
          className="font-mono text-sm"
          rows={20}
          disabled={readOnly || isValidating}
        />
        {isValidating && (
          <div className="text-sm text-muted-foreground">Validating...</div>
        )}
      </TabsContent>
    </Tabs>
  );
}

interface QuestionCardProps {
  question: Question;
  onUpdate: (updated: Question) => void;
  onRemove: () => void;
  readOnly?: boolean;
}

function QuestionCard({
  question,
  onUpdate,
  onRemove,
  readOnly = false,
}: QuestionCardProps) {
  return (
    <div className="rounded-lg border p-4 space-y-4">
      <div className="flex items-start justify-between">
        <div className="flex-1 space-y-3">
          {/* Question Kind and ID */}
          <div className="grid gap-3 md:grid-cols-3">
            <div>
              <label className="text-sm font-medium">Type</label>
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
                disabled={readOnly}
              >
                <SelectTrigger className="mt-1">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="select">Select (pick one)</SelectItem>
                  <SelectItem value="judge">Judge (yes/no)</SelectItem>
                  <SelectItem value="score">Score (rate on scale)</SelectItem>
                </SelectContent>
              </Select>
              <HelperText className="mt-1">
                select: choose from options; judge: binary yes/no; score: numeric rating.
              </HelperText>
            </div>

            <div>
              <label className="text-sm font-medium">Question ID</label>
              <Input
                value={question.id}
                onChange={(e) =>
                  onUpdate({ ...question, id: e.target.value })
                }
                disabled={readOnly}
                className="mt-1"
              />
              <HelperText className="mt-1">
                Unique identifier for this question.
              </HelperText>
            </div>
          </div>

          {/* Instructions */}
          <div>
            <label className="text-sm font-medium">Instructions</label>
            <Textarea
              value={question.instructions}
              onChange={(e) =>
                onUpdate({ ...question, instructions: e.target.value })
              }
              disabled={readOnly}
              className="mt-1"
              rows={2}
              placeholder="What should the model decide about?"
            />
            <HelperText className="mt-1">
              Clear question or instruction for the model to answer.
            </HelperText>
          </div>

          {/* Judge-specific fields */}
          {question.kind === 'judge' && (
            <div className="space-y-3 border-t pt-3">
              <div>
                <label className="text-sm font-medium">Positive criteria</label>
                <Textarea
                  value={question.positive_criteria || ''}
                  onChange={(e) =>
                    onUpdate({
                      ...question,
                      positive_criteria: e.target.value,
                    })
                  }
                  disabled={readOnly}
                  className="mt-1"
                  rows={2}
                  placeholder="What makes this true?"
                />
                <HelperText className="mt-1">
                  Precise criteria that must be met for a yes answer.
                </HelperText>
              </div>

              <div>
                <label className="text-sm font-medium">Negative criteria</label>
                <Textarea
                  value={question.negative_criteria || ''}
                  onChange={(e) =>
                    onUpdate({
                      ...question,
                      negative_criteria: e.target.value,
                    })
                  }
                  disabled={readOnly}
                  className="mt-1"
                  rows={2}
                  placeholder="What makes this false?"
                />
                <HelperText className="mt-1">
                  Criteria that make a no answer correct.
                </HelperText>
              </div>
            </div>
          )}

          {/* Options for select and score */}
          {(question.kind === 'select' || question.kind === 'score') && (
            <div className="space-y-3 border-t pt-3">
              <div className="flex items-center justify-between">
                <label className="text-sm font-medium">Options</label>
                <Badge variant="outline">{question.options.length} options</Badge>
              </div>

              <div className="space-y-2">
                {question.options.map((option, optIndex) => (
                  <div key={optIndex} className="flex gap-2">
                    <Input
                      placeholder="Option ID"
                      value={option.id}
                      onChange={(e) => {
                        const updated = [...question.options];
                        updated[optIndex] = {
                          ...option,
                          id: e.target.value,
                        };
                        onUpdate({ ...question, options: updated });
                      }}
                      disabled={readOnly}
                      className="flex-1"
                    />
                    <Input
                      placeholder="Description"
                      value={option.description}
                      onChange={(e) => {
                        const updated = [...question.options];
                        updated[optIndex] = {
                          ...option,
                          description: e.target.value,
                        };
                        onUpdate({ ...question, options: updated });
                      }}
                      disabled={readOnly}
                      className="flex-1"
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        const updated = question.options.filter(
                          (_, i) => i !== optIndex
                        );
                        onUpdate({ ...question, options: updated });
                      }}
                      disabled={readOnly || question.options.length <= 1}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                ))}
              </div>

              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => {
                  const newOption = {
                    id: `option${question.options.length + 1}`,
                    description: '',
                  };
                  onUpdate({
                    ...question,
                    options: [...question.options, newOption],
                  });
                }}
                disabled={readOnly}
                className="w-full"
              >
                <Plus className="mr-2 h-4 w-4" />
                Add option
              </Button>
            </div>
          )}
        </div>

        {/* Remove button */}
        <div className="pt-2 border-t">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onRemove}
            disabled={readOnly}
            className="text-destructive hover:text-destructive"
          >
            <Trash2 className="mr-2 h-4 w-4" />
            Remove question
          </Button>
        </div>
      </div>
    </div>
  );
}
