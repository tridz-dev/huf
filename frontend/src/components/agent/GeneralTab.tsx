import { FormField, FormItem, FormLabel, FormControl, FormDescription, FormMessage } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Slider } from '@/components/ui/slider';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { UseFormReturn } from 'react-hook-form';
import { Badge } from '@/components/ui/badge';
import type { AIProvider, AIModel } from '@/types/agent.types';
import type { AgentFormValues } from './types';
import { InstructionsTextarea } from './InstructionsTextarea';
import { SectionRailLayout, SectionBlock, type RailSection } from './form-base/SectionRailLayout';

interface GeneralTabProps {
  form: UseFormReturn<AgentFormValues>;
  providers: AIProvider[];
  models: AIModel[];
  watchProvider: string;
  optimizingPrompt: boolean;
  onOptimizePrompt: () => void;
}

export function GeneralTab({ form, providers, models, watchProvider, optimizingPrompt, onOptimizePrompt }: GeneralTabProps) {
  const agentName = form.watch('agent_name');
  const provider = form.watch('provider');
  const model = form.watch('model');
  const instructions = form.watch('instructions');

  const sections: RailSection[] = [
    {
      id: 'identity',
      label: 'Identity',
      status: agentName ? 'complete' : 'empty',
      meta: agentName || 'Name required',
    },
    {
      id: 'model',
      label: 'Model',
      status: provider && model ? 'complete' : provider ? 'partial' : 'empty',
      meta: model || provider || 'Pick provider + model',
    },
    {
      id: 'instructions',
      label: 'Instructions',
      status: instructions ? 'complete' : 'partial',
      meta: instructions ? `${instructions.length} chars` : 'Add system prompt',
    },
  ];

  return (
    <SectionRailLayout sections={sections}>
      <SectionBlock id="identity" title="Identity" description="Name and describe the agent's purpose.">
        <FormField
          control={form.control}
          name="agent_name"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Agent Name</FormLabel>
              <FormControl>
                <Input placeholder="my-agent" {...field} />
              </FormControl>
              <FormDescription>Unique agent name</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="description"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Description</FormLabel>
              <FormControl>
                <Input
                  placeholder="A short summary describing what this agent does."
                  {...field}
                  value={field.value ?? ''}
                />
              </FormControl>
              <FormDescription>A concise summary shown in listings and docs.</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
      </SectionBlock>

      <SectionBlock id="model" title="Model" description="Provider, model, and response randomness.">
        <div className="grid gap-4 sm:grid-cols-2">
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
                    {providers.map((item) => (
                      <SelectItem key={item.name} value={item.name}>
                        {item.provider_name || item.name}
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
                <Select onValueChange={field.onChange} value={field.value} disabled={!watchProvider}>
                  <FormControl>
                    <SelectTrigger>
                      <SelectValue placeholder="Select model" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    {models
                      .filter((item) => item.provider === watchProvider)
                      .map((item) => (
                        <SelectItem key={item.name} value={item.name}>
                          {item.model_name || item.name}
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
                <div className="flex items-center justify-between">
                  <FormLabel>Temperature</FormLabel>
                  <Badge variant="outline">{field.value}</Badge>
                </div>
                <FormControl>
                  <Slider min={0} max={2} step={0.1} value={[field.value]} onValueChange={(vals) => field.onChange(vals[0])} />
                </FormControl>
                <FormDescription>Lower = focused, higher = creative</FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="top_p"
            render={({ field }) => (
              <FormItem>
                <div className="flex items-center justify-between">
                  <FormLabel>Top P</FormLabel>
                  <Badge variant="outline">{field.value}</Badge>
                </div>
                <FormControl>
                  <Slider min={0} max={1} step={0.05} value={[field.value]} onValueChange={(vals) => field.onChange(vals[0])} />
                </FormControl>
                <FormDescription>Nucleus sampling parameter</FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>
      </SectionBlock>

      <SectionBlock id="instructions" title="Instructions" description="System prompt, goals, and constraints.">
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
      </SectionBlock>
    </SectionRailLayout>
  );
}
