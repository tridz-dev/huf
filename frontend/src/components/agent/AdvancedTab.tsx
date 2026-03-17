import { FormField, FormItem, FormLabel, FormControl, FormDescription, FormMessage } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { UseFormReturn } from 'react-hook-form';
import type { AgentFormValues } from './types';
import type { AIModel } from '@/types/agent.types';

interface AdvancedTabProps {
  form: UseFormReturn<AgentFormValues>;
  allModels: AIModel[];
}

function modelSupports(model: AIModel, required: string): boolean {
  return (model.modalities || '').trim() === required;
}

export function AdvancedTab({ form, allModels }: AdvancedTabProps) {
  const imageModels = allModels.filter((m) => modelSupports(m, 'Image'));
  const ttsModels = allModels.filter((m) => modelSupports(m, 'Text-to-Speech'));
  const sttModels = allModels.filter((m) => modelSupports(m, 'Transcription'));

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
                    onCheckedChange={field.onChange}
                  />
                </FormControl>
              </FormItem>
            )}
          />

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
                <FormLabel>Image Generation Model</FormLabel>
                <Select
                  onValueChange={(v) => field.onChange(v || undefined)}
                  value={field.value || ''}
                >
                  <FormControl>
                    <SelectTrigger>
                      <SelectValue placeholder="Select image model (optional)" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    {imageModels.map((m) => (
                      <SelectItem key={m.name} value={m.name}>
                        {m.model_name || m.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FormDescription>Only models tagged with modality “Image” are shown.</FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="tts_model"
            render={({ field }) => (
              <FormItem>
                <FormLabel>TTS Model</FormLabel>
                <Select
                  onValueChange={(v) => field.onChange(v || undefined)}
                  value={field.value || ''}
                >
                  <FormControl>
                    <SelectTrigger>
                      <SelectValue placeholder="Select TTS model (optional)" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    {ttsModels.map((m) => (
                      <SelectItem key={m.name} value={m.name}>
                        {m.model_name || m.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FormDescription>Only models tagged with modality “Text-to-Speech” are shown.</FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="tts_voice"
            render={({ field }) => (
              <FormItem>
                <FormLabel>TTS Voice</FormLabel>
                <FormControl>
                  <Input placeholder="e.g. alloy, nova, 21m00Tcm4TlvDq8ikWAM" {...field} value={field.value || ''} />
                </FormControl>
                <FormDescription>Optional voice identifier for the selected TTS provider.</FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="stt_model"
            render={({ field }) => (
              <FormItem>
                <FormLabel>STT Model</FormLabel>
                <Select
                  onValueChange={(v) => field.onChange(v || undefined)}
                  value={field.value || ''}
                >
                  <FormControl>
                    <SelectTrigger>
                      <SelectValue placeholder="Select transcription model (optional)" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    {sttModels.map((m) => (
                      <SelectItem key={m.name} value={m.name}>
                        {m.model_name || m.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FormDescription>Only models tagged with modality “Transcription” are shown.</FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
        </CardContent>
      </Card>
    </div>
  );
}
