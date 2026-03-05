import { FormField, FormItem, FormLabel, FormControl, FormDescription, FormMessage } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Slider } from '@/components/ui/slider';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';
import { UseFormReturn } from 'react-hook-form';
import type { AIProvider, AIModel } from '@/types/agent.types';
import type { AgentFormValues } from './types';
import { InstructionsTextarea } from './InstructionsTextarea';
import { Checkbox } from '../ui/checkbox';

interface GeneralTabProps {
  form: UseFormReturn<AgentFormValues>;
  providers: AIProvider[];
  models: AIModel[];
  watchProvider: string;
  optimizingPrompt: boolean;
  onOptimizePrompt: () => void;
}

export function GeneralTab({ form, providers, models, watchProvider, optimizingPrompt, onOptimizePrompt }: GeneralTabProps) {
  const watchEnablePromptCaching = form.watch("enable_prompt_caching");
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>LLM Configuration</CardTitle>
          <CardDescription>Configure language model settings</CardDescription>
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
                  <FormDescription>Unique agent name</FormDescription>
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
                          <FormDescription>A brief description of the agent's purpose</FormDescription>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </AccordionContent>
                </AccordionItem>
              </Accordion>
            </div>
          </div>
          <FormField
            control={form.control}
            name="provider"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Provider</FormLabel>
                <Select
                  onValueChange={(value) => {
                    field.onChange(value);
                    form.setValue('model', '');
                  }}
                  value={field.value}
                >
                  <FormControl>
                    <SelectTrigger>
                      <SelectValue placeholder="Select provider" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    {providers.map((provider) => (
                      <SelectItem key={provider.name} value={provider.name}>
                        {provider.provider_name || provider.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
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
                <Select
                  onValueChange={field.onChange}
                  value={field.value}
                  disabled={!watchProvider}
                >
                  <FormControl>
                    <SelectTrigger>
                      <SelectValue placeholder="Select model" />
                    </SelectTrigger>
                  </FormControl>
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
                <FormDescription>Filtered by selected provider</FormDescription>
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
                  <Slider
                    min={0}
                    max={2}
                    step={0.1}
                    value={[field.value]}
                    onValueChange={(vals) => field.onChange(vals[0])}
                  />
                </FormControl>
                <FormDescription>
                  Lower = focused, higher = creative
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
                  <Slider
                    min={0}
                    max={1}
                    step={0.05}
                    value={[field.value]}
                    onValueChange={(vals) => field.onChange(vals[0])}
                  />
                </FormControl>
                <FormDescription>
                  Nucleus sampling parameter
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="enable_prompt_caching"
            render={({ field }) => (
              <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4 sm:col-span-2">
                <div className="space-y-0.5">
                  <FormLabel className="text-base">Enable Prompt Caching</FormLabel>
                  <FormDescription>
                    Enable prompt caching to cache repeated prompt content and reduce token costs. Only works with supported providers (OpenAI, Anthropic, Bedrock, Deepseek).
                  </FormDescription>
                </div>
                <FormControl>
                  <Switch
                    checked={field.value ?? false}
                    onCheckedChange={field.onChange}
                  />
                </FormControl>
              </FormItem>
            )}
          />
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
                    Cache control type: 'ephemeral' for Anthropic (charges for cache writes), 'auto' for OpenAI/Deepseek (automatic caching).
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
                <FormItem className="flex items-center space-x-3">
                  <FormControl>
                    <Checkbox
                      checked={field.value}
                      onCheckedChange={field.onChange}
                    />
                  </FormControl>
                  <div className="space-y-1 leading-none">
                    <FormLabel>Cache System Message</FormLabel>
                    <FormDescription>
                      Cache the system message/instructions to avoid re-sending them on every request.
                    </FormDescription>
                  </div>
                </FormItem>
              )}
            />
          )}
          {watchEnablePromptCaching && (
            <FormField
              control={form.control}
              name="cache_conversation_history"
              render={({ field }) => (
                <FormItem className="flex items-center space-x-3">
                  <FormControl>
                    <Checkbox
                      checked={field.value}
                      onCheckedChange={field.onChange}
                    />
                  </FormControl>
                  <div className="space-y-1 leading-none">
                    <FormLabel>Cache Conversation History</FormLabel>
                    <FormDescription>
                      Cache conversation history messages to reduce token usage in multi-turn conversations.
                    </FormDescription>
                  </div>
                </FormItem>
              )}
            />
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Prompt</CardTitle>
          <CardDescription>Define system prompt, goal, and constraints. Use 'Local' for inline prompts or 'Template' to link a reusable prompt from the library.</CardDescription>
        </CardHeader>

        <CardContent className="grid gap-6 sm:grid-cols-2">

          <FormField
            control={form.control}
            name="prompt_mode"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Prompt Mode</FormLabel>

                <Select
                  onValueChange={field.onChange}
                  value={field.value}
                >
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

                <FormDescription> "Local" uses the instructions
                  field below. "Template" links to a reusable Agent Prompt.
                </FormDescription>

                <FormMessage />
              </FormItem>
            )}
          />

          {form.watch("prompt_mode") === "Template" && (
            <FormField
              control={form.control}
              name="agent_prompt"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Agent Prompt</FormLabel>

                  <Select
                    onValueChange={field.onChange}
                    value={field.value}
                  >
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="Select Agent Prompt" />
                      </SelectTrigger>
                    </FormControl>

                    <SelectContent>
                      {/* Replace with API data later */}
                      <SelectItem value="prompt_1">Prompt 1</SelectItem>
                      <SelectItem value="prompt_2">Prompt 2</SelectItem>
                    </SelectContent>
                  </Select>

                  <FormDescription>
                    Link to a reusable prompt template from the Agent Prompt library.
                  </FormDescription>

                  <FormMessage />
                </FormItem>
              )}
            />
          )}

          {form.watch("prompt_mode") === "Template" && (
            <FormField
              control={form.control}
              name="prompt_version_locked"
              render={({ field }) => (
                <FormItem className="flex items-center space-x-3 sm:col-span-2">
                  <FormControl>
                    <Checkbox
                      checked={field.value || false}
                      onCheckedChange={field.onChange}
                    />
                  </FormControl>

                  <div className="space-y-1 leading-none">
                    <FormLabel>Lock Prompt Version</FormLabel>

                    <FormDescription>
                      If checked, this agent will stay on the prompt version it was attached to,
                      ignoring newer versions.
                    </FormDescription>
                  </div>

                </FormItem>
              )}
            />
          )}

          {form.watch("prompt_mode") === "Template" && (
            <FormField
              control={form.control}
              name="attached_at_version"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Attached At Version</FormLabel>

                  <FormControl>
                    <Input
                      type="number"
                      value={field.value ?? ""}
                      disabled
                    />
                  </FormControl>

                  <FormDescription>
                    Version of the prompt template currently attached to this agent.
                  </FormDescription>

                  <FormMessage />
                </FormItem>
              )}
            />
          )}
        </CardContent>
      </Card>

      {form.watch("prompt_mode") === "Local" && (
        <Card>
          <CardHeader>
            <CardTitle>Instructions</CardTitle>
            <CardDescription>Define system prompt, goals, and constraints</CardDescription>
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
                  />
                  <FormMessage />
                </FormItem>
              )}
            />
          </CardContent>
        </Card>
      )}
    </div>
  );
}

