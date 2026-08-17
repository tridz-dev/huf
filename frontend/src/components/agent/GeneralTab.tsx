import { useState, useEffect } from 'react';
import { FormField, FormItem, FormLabel, FormControl, FormDescription, FormMessage } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Slider } from '@/components/ui/slider';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert';
import { AlertTriangle, Plus, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { UseFormReturn } from 'react-hook-form';
import type { AIProvider, AIModel } from '@/types/agent.types';
import type { AgentFormValues } from './types';
import { InstructionsTextarea } from './InstructionsTextarea';
import { PromptTemplateSection, type AgentPromptOption } from './PromptTemplateSection';
import { LinkFieldControl } from '@/components/ui/link-field-control';
import { linkRoutes } from '@/lib/link-routes';
import { checkCacheableModels, type CacheableModelsResponse } from '@/services/agentApi';

interface GeneralTabProps {
  form: UseFormReturn<AgentFormValues>;
  providers: AIProvider[];
  models: AIModel[];
  watchProvider: string | undefined;
  optimizingPrompt: boolean;
  onOptimizePrompt: () => void;
  promptOptions: AgentPromptOption[];
  loadingPrompts: boolean;
  showAddNewPrompt?: boolean;
  /** True when protected fields must be read-only (system agent + non-admin). */
  locked?: boolean;
}

export function GeneralTab({
  form,
  providers,
  models,
  watchProvider,
  optimizingPrompt,
  onOptimizePrompt,
  promptOptions,
  loadingPrompts,
  showAddNewPrompt = true,
  locked = false,
}: GeneralTabProps) {
  const watchEnablePromptCaching = form.watch('enable_prompt_caching');
  const watchModel = form.watch('model');
  const promptMode = form.watch('prompt_mode');
  const watchModality = form.watch('agent_modality');
  const isVoiceOnly = watchModality === 'Voice';

  const [cacheStatus, setCacheStatus] = useState<CacheableModelsResponse | null>(null);

  useEffect(() => {
    if (!watchEnablePromptCaching || !watchProvider || !watchModel) {
      setCacheStatus(null);
      return;
    }
    let cancelled = false;
    checkCacheableModels(watchProvider, watchModel).then((res) => {
      if (!cancelled) {
        setCacheStatus(res);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [watchEnablePromptCaching, watchProvider, watchModel]);

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Modality</CardTitle>
          <CardDescription>
            What this agent talks to users through. Voice-only hides text/LLM settings that a
            realtime voice call doesn&apos;t use; Text-only hides voice settings.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <FormField
            control={form.control}
            name="agent_modality"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Modality</FormLabel>
                <Select onValueChange={field.onChange} value={field.value} disabled={locked}>
                  <FormControl>
                    <SelectTrigger>
                      <SelectValue placeholder="Select modality" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    <SelectItem value="Text">Text only</SelectItem>
                    <SelectItem value="Voice">Voice only</SelectItem>
                    <SelectItem value="Both">Text and Voice</SelectItem>
                  </SelectContent>
                </Select>
                <FormDescription>
                  {field.value === 'Voice'
                    ? 'This agent only handles realtime voice calls. Tools, knowledge, skills, and text-model settings are hidden.'
                    : field.value === 'Text'
                      ? 'This agent only handles text chat. Voice/TTS settings are hidden.'
                      : 'This agent handles both text chat and voice calls.'}
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Agent Identity</CardTitle>
          <CardDescription>Name and description for this agent.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <FormField
              control={form.control}
              name="agent_name"
              render={({ field }) => (
                <FormItem className="sm:col-span-2">
                  <FormLabel>Agent Name</FormLabel>
                  <FormControl>
                    <Input placeholder="my-agent" {...field} />
                  </FormControl>
                  <FormDescription>A unique name for this agent.</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="sm:col-span-2">
              <Accordion type="single" collapsible className="w-full">
                <AccordionItem value="description">
                  <AccordionTrigger>Description</AccordionTrigger>
                  <AccordionContent>
                    <FormField
                      control={form.control}
                      name="description"
                      render={({ field }) => (
                        <FormItem>
                          <FormControl>
                            <Textarea
                              placeholder="A short summary describing what this agent does or is designed for."
                              className="min-h-[80px] resize-y"
                              {...field}
                            />
                          </FormControl>
                          <FormDescription>A short summary describing what this agent does or is designed for.</FormDescription>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </AccordionContent>
                </AccordionItem>
              </Accordion>
            </div>
          </div>
        </CardContent>
      </Card>

      {!isVoiceOnly && (
      <Card>
        <CardHeader>
          <CardTitle>LLM Configuration</CardTitle>
          <CardDescription>Configure language model settings</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6 sm:grid-cols-2">
          <FormField
            control={form.control}
            name="provider"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Provider</FormLabel>
                <FormControl>
                  <LinkFieldControl value={field.value} linkTo={linkRoutes.aiProvider}>
                    <Select
                      onValueChange={(value) => {
                        field.onChange(value);
                        form.setValue('model', '');
                      }}
                      value={field.value || undefined}
                      disabled={locked}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Select provider" />
                      </SelectTrigger>
                      <SelectContent>
                        {providers.map((provider) => (
                          <SelectItem key={provider.name} value={provider.name}>
                            {provider.provider_name || provider.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </LinkFieldControl>
                </FormControl>
                <FormDescription>The AI provider that will power this agent (e.g., OpenAI, OpenRouter).</FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="model"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Model</FormLabel>
                <FormControl>
                  <LinkFieldControl value={field.value} linkTo={linkRoutes.aiModel} disabled={!watchProvider}>
                    <Select onValueChange={field.onChange} value={field.value || undefined} disabled={!watchProvider || locked}>
                      <SelectTrigger>
                        <SelectValue placeholder="Select model" />
                      </SelectTrigger>
                      <SelectContent>
                        {models
                          .filter((model) => model.provider === watchProvider)
                          .map((model) => (
                            <SelectItem key={model.name} value={model.name}>
                              {model.model_name || model.name}
                            </SelectItem>
                          ))}
                      </SelectContent>
                    </Select>
                  </LinkFieldControl>
                </FormControl>
                <FormDescription>The specific AI model to use from the selected provider (e.g., gpt-4-turbo).</FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="temperature"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Temperature: {field.value}</FormLabel>
                <FormControl>
                  <Slider min={0} max={2} step={0.1} value={[field.value]} onValueChange={(vals) => field.onChange(vals[0])} />
                </FormControl>
                <FormDescription>
                  What sampling temperature to use, between 0 and 2. Higher values like 0.8 will make the output more random, while lower values like 0.2 will make it more focused and deterministic.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="top_p"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Top P: {field.value}</FormLabel>
                <FormControl>
                  <Slider min={0} max={1} step={0.05} value={[field.value]} onValueChange={(vals) => field.onChange(vals[0])} />
                </FormControl>
                <FormDescription className="whitespace-pre-line">
                  {`An alternative to sampling with temperature, called nucleus sampling, where the model considers the results of the tokens with top_p probability mass. So 0.1 means only the tokens comprising the top 10% probability mass are considered.

We generally recommend altering this or temperature but not both.`}
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="run_immediately"
            render={({ field }) => (
              <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4 sm:col-span-2">
                <div className="space-y-0.5 pr-4">
                  <FormLabel className="text-base">Run Immediately</FormLabel>
                  <FormDescription>
                    When enabled, agent runs execute synchronously and return a direct response. When disabled (default), runs are queued to avoid holding web workers during long LLM and tool calls. Enable only for trusted calls that require an immediate response.
                  </FormDescription>
                </div>
                <FormControl>
                  <Switch checked={field.value ?? false} onCheckedChange={field.onChange} />
                </FormControl>
              </FormItem>
            )}
          />
        </CardContent>
      </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Prompt Source</CardTitle>
          <CardDescription>Choose whether this agent uses inline instructions or a reusable prompt template.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6 sm:grid-cols-2">
          <FormField
            control={form.control}
            name="prompt_mode"
            render={({ field }) => (
              <FormItem className="sm:col-span-2">
                <FormLabel>Prompt Mode</FormLabel>
                <Select onValueChange={field.onChange} value={field.value} disabled={locked}>
                  <FormControl>
                    <SelectTrigger>
                      <SelectValue placeholder="Select prompt mode" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    <SelectItem value="Local">Local</SelectItem>
                    <SelectItem value="Template">Template</SelectItem>
                  </SelectContent>
                </Select>
                <FormDescription>
                  How this agent&apos;s prompt is managed. &apos;Local&apos; uses the instructions field below. &apos;Template&apos; links to a reusable Agent Prompt.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
        </CardContent>
      </Card>

      {promptMode === 'Local' ? (
        <Card>
          <CardHeader>
            <CardTitle>Instructions</CardTitle>
            <CardDescription>
              Define system prompt, goal, and constraints. Use &apos;Local&apos; for inline prompts or &apos;Template&apos; to link a reusable prompt from the library.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <FormField
              control={form.control}
              name="instructions"
              render={({ field }) => (
                <FormItem>
                  <InstructionsTextarea
                    form={form}
                    field={field}
                    optimizingPrompt={optimizingPrompt}
                    onOptimizePrompt={onOptimizePrompt}
                    showOptimize={true}
                    showExpand={true}
                    disabled={locked}
                  />
                  <FormDescription>
                    The system prompt or instructions that define the agent&apos;s personality, goals, and constraints. This is the core logic of the agent.
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
          </CardContent>
        </Card>
      ) : (
        <PromptTemplateSection
          form={form}
          promptOptions={promptOptions}
          loadingPrompts={loadingPrompts}
          showAddNew={showAddNewPrompt}
          locked={locked}
        />
      )}

      {!isVoiceOnly && (
      <Card>
        <CardHeader>
          <CardTitle>Starter Prompts</CardTitle>
          <CardDescription>
            Up to 3 starter prompts shown to users when starting a chat with this agent.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {form.watch('starter_prompts')?.map((_row, index) => (
            <div key={index} className="flex items-start gap-2">
              <FormField
                control={form.control}
                name={`starter_prompts.${index}.prompt_text`}
                render={({ field }) => (
                  <FormItem className="flex-1">
                    <FormControl>
                      <Textarea
                        placeholder="Enter a starter prompt"
                        className="min-h-[60px] resize-y"
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={() => {
                  const current = form.getValues('starter_prompts') || [];
                  form.setValue(
                    'starter_prompts',
                    current.filter((_r, i) => i !== index),
                    { shouldDirty: true }
                  );
                }}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          ))}
          {(form.watch('starter_prompts') || []).length < 3 && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => {
                const current = form.getValues('starter_prompts') || [];
                if (current.length >= 3) return;
                form.setValue(
                  'starter_prompts',
                  [...current, { prompt_text: '' }],
                  { shouldDirty: true }
                );
              }}
            >
              <Plus className="h-4 w-4 mr-1" />
              Add starter prompt
            </Button>
          )}
        </CardContent>
      </Card>
      )}

      {!isVoiceOnly && (
      <Card>
        <CardHeader>
          <CardTitle>Prompt Caching</CardTitle>
          <CardDescription>
            Configure prompt caching to reduce costs by caching repeated prompt content
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6 sm:grid-cols-2">
          <FormField
            control={form.control}
            name="enable_prompt_caching"
            render={({ field }) => (
              <FormItem className="flex flex-row items-center justify-between rounded-none border p-4 sm:col-span-2">
                <div className="space-y-0.5">
                  <FormLabel className="text-base">Enable Prompt Caching</FormLabel>
                  <FormDescription>
                    Enable prompt caching to cache repeated prompt content and reduce token costs. Only works with supported providers (OpenAI, Anthropic, Bedrock, Deepseek).
                  </FormDescription>
                </div>
                <FormControl>
                  <Switch checked={field.value ?? false} onCheckedChange={field.onChange} />
                </FormControl>
              </FormItem>
            )}
          />

          {watchEnablePromptCaching && watchProvider && watchModel && cacheStatus && !cacheStatus.supported && (
            <Alert className="sm:col-span-2 border-amber-500/50 bg-amber-500/10 text-amber-900 dark:text-amber-200">
              <AlertTriangle className="h-4 w-4 text-amber-600 dark:text-amber-400" />
              <AlertTitle className="font-semibold text-sm">Silent Degradation Warning: Prompt Caching Not Supported</AlertTitle>
              <AlertDescription className="text-xs mt-1 space-y-1">
                <p>
                  The selected model <strong>{watchModel}</strong> does not support prompt caching for provider <strong>{watchProvider}</strong>. Prompt caching will be silently skipped during execution.
                </p>
                {cacheStatus.alternatives.length > 0 && (
                  <p className="text-steel-soft">
                    Supported alternative models for {watchProvider}: {cacheStatus.alternatives.slice(0, 5).join(', ')}
                  </p>
                )}
              </AlertDescription>
            </Alert>
          )}

          {watchEnablePromptCaching && (
            <FormField
              control={form.control}
              name="cache_control_type"
              render={({ field }) => (
                <FormItem className="sm:col-span-2">
                  <FormLabel>Cache Control Type</FormLabel>
                  <Select onValueChange={field.onChange} value={field.value}>
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="Select cache control type" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      <SelectItem value="auto">Auto</SelectItem>
                      <SelectItem value="ephemeral">Ephemeral</SelectItem>
                    </SelectContent>
                  </Select>
                  <FormDescription>
                    Cache control type: &apos;ephemeral&apos; for Anthropic (charges for cache writes), &apos;auto&apos; for OpenAI/Deepseek (automatic caching).
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
          )}

          {watchEnablePromptCaching && (
            <FormField
              control={form.control}
              name="cache_system_message"
              render={({ field }) => (
                <FormItem className="flex flex-row items-center justify-between rounded-none border p-4 sm:col-span-2">
                  <div className="space-y-0.5">
                    <FormLabel className="text-base">Cache System Message</FormLabel>
                    <FormDescription>
                      Cache the system message/instructions to avoid re-sending them on every request.
                    </FormDescription>
                  </div>
                  <FormControl>
                    <Switch checked={field.value ?? false} onCheckedChange={field.onChange} />
                  </FormControl>
                </FormItem>
              )}
            />
          )}

          {watchEnablePromptCaching && (
            <FormField
              control={form.control}
              name="cache_conversation_history"
              render={({ field }) => (
                <FormItem className="flex flex-row items-center justify-between rounded-none border p-4 sm:col-span-2">
                  <div className="space-y-0.5">
                    <FormLabel className="text-base">Cache Conversation History</FormLabel>
                    <FormDescription>
                      Cache conversation history messages to reduce token usage in multi-turn conversations.
                    </FormDescription>
                  </div>
                  <FormControl>
                    <Switch checked={field.value ?? false} onCheckedChange={field.onChange} />
                  </FormControl>
                </FormItem>
              )}
            />
          )}
        </CardContent>
      </Card>
      )}
    </div>
  );
}
