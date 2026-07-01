import { FormField, FormItem, FormLabel, FormControl, FormDescription, FormMessage } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { LinkFieldControl } from '@/components/ui/link-field-control';
import { linkRoutes } from '@/lib/link-routes';
import { Switch } from '@/components/ui/switch';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { UseFormReturn } from 'react-hook-form';
import type { AgentFormValues } from './types';
import type { AIModel } from '@/types/agent.types';
import { Combobox } from '@/components/ui/combobox';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Plus } from 'lucide-react';
import { useNavigate, useLocation } from 'react-router-dom';
import type { AgentPromptOption } from './PromptTemplateSection';
import {
	MODEL_MODALITY_IMAGE,
	MODEL_MODALITY_TTS,
	MODEL_MODALITY_STT,
	IMAGE_MODEL_LABEL,
	IMAGE_MODEL_PLACEHOLDER,
	IMAGE_MODEL_DESCRIPTION,
	TTS_MODEL_LABEL,
	TTS_MODEL_PLACEHOLDER,
	TTS_MODEL_DESCRIPTION,
	TTS_VOICE_LABEL,
	TTS_VOICE_PLACEHOLDER,
	TTS_VOICE_DESCRIPTION,
	STT_MODEL_LABEL,
	STT_MODEL_PLACEHOLDER,
	STT_MODEL_DESCRIPTION,
} from '@/data/ai';

interface AdvancedTabProps {
  form: UseFormReturn<AgentFormValues>;
  allModels: AIModel[];
  summaryPromptOptions: AgentPromptOption[];
  loadingSummaryPrompts?: boolean;
}

function modelSupports(model: AIModel, required: string): boolean {
  return (model.modalities || '').trim() === required;
}

export function AdvancedTab({
  form,
  allModels,
  summaryPromptOptions,
  loadingSummaryPrompts = false,
}: AdvancedTabProps) {
	const imageModels = allModels.filter((m) => modelSupports(m, MODEL_MODALITY_IMAGE));
	const ttsModels = allModels.filter((m) => modelSupports(m, MODEL_MODALITY_TTS));
	const sttModels = allModels.filter((m) => modelSupports(m, MODEL_MODALITY_STT));
	const contextStrategy = form.watch('context_strategy');
	const summaryPromptMode = form.watch('summary_prompt_mode');
	const navigate = useNavigate();
	const location = useLocation();
	const selectedSummaryPrompt = summaryPromptOptions.find((option) => option.value === form.watch('summary_prompt_template'));
	const summaryPromptComboboxOptions = summaryPromptOptions.map((option) => ({
		...option,
		subtitle: option.version ? `Version ${option.version}` : undefined,
	}));

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Context Settings</CardTitle>
          <CardDescription>Configure how the agent handles conversation history and context</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6 sm:grid-cols-2">
          <FormField
            control={form.control}
            name="context_strategy"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Context Strategy</FormLabel>
                <Select onValueChange={field.onChange} value={field.value || ''}>
                  <FormControl>
                    <SelectTrigger>
                      <SelectValue placeholder="Select strategy" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    <SelectItem value="None">None</SelectItem>
                    <SelectItem value="Summarize">Summarize</SelectItem>
                    <SelectItem value="FIFO">FIFO</SelectItem>
                  </SelectContent>
                </Select>
                <FormDescription>
                  How to handle conversation history when it exceeds the limit. 'Summarize' compresses old messages, 'FIFO' drops them.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="summary_ratio"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Summary Ratio</FormLabel>
                <FormControl>
                  <Input
                    type="text"
                    placeholder="0.7"
                    {...field}
                    value={field.value?.toString() || ''}
                    onChange={(e) => {
                      const value = e.target.value;
                      if (value === '') {
                        field.onChange(undefined);
                      } else {
                        const numValue = parseFloat(value);
                        if (!isNaN(numValue)) {
                          field.onChange(numValue);
                        }
                      }
                    }}
                  />
                </FormControl>
                <FormDescription>
                  Ratio of history to summarize effectively. 0.7 means 70% of oldest messages.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          {contextStrategy === 'Summarize' && (
            <FormField
              control={form.control}
              name="summary_model"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Summary Model</FormLabel>
                  <FormControl>
                    <LinkFieldControl value={field.value} linkTo={linkRoutes.aiModel}>
                      <Select
                        onValueChange={(v) => field.onChange(v || undefined)}
                        value={field.value || ''}
                      >
                        <SelectTrigger>
                          <SelectValue placeholder="Default (main agent model)" />
                        </SelectTrigger>
                        <SelectContent>
                          {allModels.map((m) => (
                            <SelectItem key={m.name} value={m.name}>
                              {m.model_name || m.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </LinkFieldControl>
                  </FormControl>
                  <FormDescription>
                    Optional lightweight model used only when compressing older messages (Summarize strategy).
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
          )}

          {contextStrategy === 'Summarize' && (
            <FormField
              control={form.control}
              name="summary_prompt_mode"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Summary Prompt Mode</FormLabel>
                  <Select onValueChange={field.onChange} value={field.value || ''}>
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="Select mode" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      <SelectItem value="Local">Local</SelectItem>
                      <SelectItem value="Template">Template</SelectItem>
                    </SelectContent>
                  </Select>
                  <FormDescription>
                    Use a local summary prompt or link to a reusable Agent Summary Prompt template.
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
          )}

          {contextStrategy === 'Summarize' && summaryPromptMode === 'Template' && (
            <FormField
              control={form.control}
              name="summary_prompt_template"
              render={({ field }) => (
                <FormItem id="summary-prompt-template-field" className="sm:col-span-2">
                  <FormLabel>Summary Prompt Template</FormLabel>
                  <div className="flex items-center gap-2">
                    <FormControl>
                      <Combobox
                        options={summaryPromptComboboxOptions}
                        value={field.value}
                        onValueChange={field.onChange}
                        placeholder={loadingSummaryPrompts ? 'Loading templates...' : 'Select an Agent Summary Prompt'}
                        disabled={loadingSummaryPrompts}
                        searchPlaceholder="Search summary templates..."
                        emptyText="No active summary prompt templates found."
                        linkTo={linkRoutes.agentSummaryPrompt}
                      />
                    </FormControl>
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={() =>
                        (() => {
                          const returnTo = `${location.pathname}#advanced`;
                          const selectedPromptField = 'summary_prompt_template';
                          try {
                            localStorage.setItem(
                              'agentSummaryPromptCreateReturnTo',
                              JSON.stringify({ returnTo, selectedPromptField })
                            );
                          } catch {
                            // ignore storage failures
                          }
                          navigate('/summary-prompts/new', {
                            state: {
                              returnTo,
                              selectedPromptField,
                              showTab: 'advanced',
                            },
                          });
                        })()
                      }
                    >
                      <Plus className="w-4 h-4 mr-2" />
                      New
                    </Button>
                  </div>
                  <FormDescription>
                    Pick an active summary prompt template from the shared library. The backend records the current
                    version when you attach it.
                  </FormDescription>
                  {selectedSummaryPrompt && (
                    <div className="flex flex-wrap items-center gap-2 pt-2">
                      {selectedSummaryPrompt.version ? (
                        <Badge variant="outline">Current template v{selectedSummaryPrompt.version}</Badge>
                      ) : null}
                      {selectedSummaryPrompt.isLatest ? <Badge variant="secondary">Latest</Badge> : null}
                      {selectedSummaryPrompt.description ? (
                        <span className="text-sm text-muted-foreground">{selectedSummaryPrompt.description}</span>
                      ) : null}
                    </div>
                  )}
                  <FormMessage />
                </FormItem>
              )}
            />
          )}

          {contextStrategy === 'Summarize' && summaryPromptMode === 'Template' && (
            <FormField
              control={form.control}
              name="summary_prompt_version_locked"
              render={({ field }) => (
                <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4 sm:col-span-2">
                  <div className="space-y-0.5 pr-4">
                    <FormLabel className="text-base">Lock Summary Prompt Version</FormLabel>
                    <FormDescription>
                      Keep this agent pinned to the attached summary prompt version instead of following the
                      latest template updates automatically.
                    </FormDescription>
                  </div>
                  <FormControl>
                    <Switch checked={field.value ?? false} onCheckedChange={field.onChange} />
                  </FormControl>
                </FormItem>
              )}
            />
          )}

          {contextStrategy === 'Summarize' && summaryPromptMode === 'Template' && (
            <FormField
              control={form.control}
              name="summary_template_version_at_attach"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Summary Attached at Version</FormLabel>
                  <FormControl>
                    <div className="flex min-h-10 items-center rounded-md border bg-muted/40 px-3 text-sm text-muted-foreground">
                      {field.value ?? 'Will be recorded after template attachment'}
                    </div>
                  </FormControl>
                  <FormDescription>
                    Read-only snapshot captured by the backend when a summary prompt template is attached or changed.
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
          )}

          {contextStrategy === 'Summarize' && summaryPromptMode === 'Local' && (
            <FormField
              control={form.control}
              name="summary_prompt"
              render={({ field }) => (
                <FormItem className="sm:col-span-2">
                  <FormLabel>Summary Prompt</FormLabel>
                  <FormControl>
                    <textarea
                      className="flex min-h-[120px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                      placeholder="Enter the prompt used to summarize conversation history..."
                      {...field}
                      value={field.value || ''}
                    />
                  </FormControl>
                  <FormDescription>
                    Custom prompt for summarizing conversation history. Use {'{summary_data}'} as a placeholder
                    for the JSON input containing existing_summary and new_messages_to_incorporate.
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
          )}

          <FormField
            control={form.control}
            name="history_limit"
            render={({ field }) => (
              <FormItem>
                <FormLabel>History Limit</FormLabel>
                <FormControl>
                  <Input
                    type="number"
                    placeholder="50"
                    {...field}
                    value={field.value?.toString() || ''}
                    onChange={(e) => {
                      const value = e.target.value;
                      if (value === '') {
                        field.onChange(undefined);
                      } else {
                        const numValue = parseInt(value, 10);
                        if (!isNaN(numValue)) {
                          field.onChange(numValue);
                        }
                      }
                    }}
                  />
                </FormControl>
                <FormDescription>
                  Maximum number of messages to keep in active context before applying strategy.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="max_knowledge_tokens"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Max Knowledge Tokens</FormLabel>
                <FormControl>
                  <Input
                    type="number"
                    placeholder="2000"
                    {...field}
                    value={field.value?.toString() || ''}
                    onChange={(e) => {
                      const value = e.target.value;
                      if (value === '') {
                        field.onChange(undefined);
                      } else {
                        const numValue = parseInt(value, 10);
                        if (!isNaN(numValue)) {
                          field.onChange(numValue);
                        }
                      }
                    }}
                  />
                </FormControl>
                <FormDescription>
                  Maximum tokens to use for injected knowledge context.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="max_turns"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Max Turns</FormLabel>
                <FormControl>
                  <Input
                    type="number"
                    placeholder="10"
                    {...field}
                    value={field.value?.toString() || ''}
                    onChange={(e) => {
                      const value = e.target.value;
                      if (value === '') {
                        field.onChange(undefined);
                      } else {
                        const numValue = parseInt(value, 10);
                        if (!isNaN(numValue)) {
                          field.onChange(numValue);
                        }
                      }
                    }}
                  />
                </FormControl>
                <FormDescription>
                  Maximum consecutive turns/steps the agent can take in a single run.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="enable_conversation_data"
            render={({ field }) => (
              <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4 sm:col-span-2">
                <div className="space-y-0.5">
                  <FormLabel className="text-base">Allow Conversation Data Management</FormLabel>
                  <FormDescription>
                    If enabled, the agent can store key-value pairs in the conversation context.
                  </FormDescription>
                </div>
                <FormControl>
                  <Switch
                    checked={field.value ?? false}
                    onCheckedChange={(val) => {
                      field.onChange(val);
                      if (!val) {
                        form.setValue('inject_conversation_data', false);
                      } else {
                        form.setValue('inject_conversation_data', true);
                      }
                    }}
                  />
                </FormControl>
              </FormItem>
            )}
          />

          {form.watch('enable_conversation_data') && (
            <FormField
              control={form.control}
              name="inject_conversation_data"
              render={({ field }) => (
                <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4 sm:col-span-2">
                  <div className="space-y-0.5">
                    <FormLabel className="text-base">Inject Conversation Data into Prompt</FormLabel>
                    <FormDescription>
                      Auto-injects all memory items into the LLM system prompt on every turn. Disabling this avoids <strong>Context Bloat</strong> (saving tokens/cost and improving latency) and lets the agent load data dynamically on-demand using the <code>get_conversation_data</code> tool.
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
          )}

          <FormField
            control={form.control}
            name="autonaming_of_conversation_title"
            render={({ field }) => (
              <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4 sm:col-span-2">
                <div className="space-y-0.5">
                  <FormLabel className="text-base">Autonaming of Conversation Title</FormLabel>
                  <FormDescription>
                    If enabled, the conversation title will be automatically updated based on the initial context.
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
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Huf UI</CardTitle>
          <CardDescription>Chat avatar styling in the agent chat interface</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6 sm:grid-cols-2">
          <FormField
            control={form.control}
            name="agent_color"
            render={({ field }) => (
              <FormItem className="sm:col-span-2">
                <FormLabel>Agent color</FormLabel>
                <div className="flex flex-wrap items-center gap-3">
                  <FormControl>
                    <Input
                      placeholder="#6366F1"
                      className="max-w-[11rem] font-mono"
                      {...field}
                      value={field.value || ''}
                    />
                  </FormControl>
                  <input
                    type="color"
                    className="h-9 w-12 cursor-pointer rounded border bg-background p-0.5"
                    value={/^#[0-9A-Fa-f]{6}$/.test(field.value || '') ? field.value : '#6366f1'}
                    onChange={(e) => field.onChange(e.target.value)}
                    aria-label="Pick agent color"
                  />
                </div>
                <FormDescription>
                  Background color for the agent avatar in chat. Include the # prefix.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="show_tool_execution_details"
            render={({ field }) => (
              <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4 sm:col-span-2">
                <div className="space-y-0.5">
                  <FormLabel className="text-base">Show Tool Execution Details</FormLabel>
                  <FormDescription>
                    Enable to display tool execution status and responses in the agent output. This includes whether each tool call is completed and its corresponding result.
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
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Model Modality Settings</CardTitle>
          <CardDescription>
            Optional: select dedicated models for image generation, audio generation (TTS), and transcription (STT).
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6 sm:grid-cols-2">
          <FormField
            control={form.control}
            name="image_generation_model"
            render={({ field }) => (
              <FormItem>
								<FormLabel>{IMAGE_MODEL_LABEL}</FormLabel>
                <FormControl>
                  <LinkFieldControl value={field.value} linkTo={linkRoutes.aiModel}>
                    <Select
                      onValueChange={(v) => field.onChange(v || undefined)}
                      value={field.value || ''}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder={IMAGE_MODEL_PLACEHOLDER} />
                      </SelectTrigger>
                      <SelectContent>
                        {imageModels.map((m) => (
                          <SelectItem key={m.name} value={m.name}>
                            {m.model_name || m.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </LinkFieldControl>
                </FormControl>
								<FormDescription>{IMAGE_MODEL_DESCRIPTION}</FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="tts_model"
            render={({ field }) => (
              <FormItem>
								<FormLabel>{TTS_MODEL_LABEL}</FormLabel>
                <FormControl>
                  <LinkFieldControl value={field.value} linkTo={linkRoutes.aiModel}>
                    <Select
                      onValueChange={(v) => field.onChange(v || undefined)}
                      value={field.value || ''}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder={TTS_MODEL_PLACEHOLDER} />
                      </SelectTrigger>
                      <SelectContent>
                        {ttsModels.map((m) => (
                          <SelectItem key={m.name} value={m.name}>
                            {m.model_name || m.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </LinkFieldControl>
                </FormControl>
								<FormDescription>{TTS_MODEL_DESCRIPTION}</FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="tts_voice"
            render={({ field }) => (
              <FormItem>
								<FormLabel>{TTS_VOICE_LABEL}</FormLabel>
                <FormControl>
									<Input placeholder={TTS_VOICE_PLACEHOLDER} {...field} value={field.value || ''} />
                </FormControl>
								<FormDescription>{TTS_VOICE_DESCRIPTION}</FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="stt_model"
            render={({ field }) => (
              <FormItem>
								<FormLabel>{STT_MODEL_LABEL}</FormLabel>
                <FormControl>
                  <LinkFieldControl value={field.value} linkTo={linkRoutes.aiModel}>
                    <Select
                      onValueChange={(v) => field.onChange(v || undefined)}
                      value={field.value || ''}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder={STT_MODEL_PLACEHOLDER} />
                      </SelectTrigger>
                      <SelectContent>
                        {sttModels.map((m) => (
                          <SelectItem key={m.name} value={m.name}>
                            {m.model_name || m.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </LinkFieldControl>
                </FormControl>
								<FormDescription>{STT_MODEL_DESCRIPTION}</FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
        </CardContent>
      </Card>
    </div>
  );
}
