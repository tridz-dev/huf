import { useEffect, useMemo, useState } from 'react';
import { useFormContext } from 'react-hook-form';
import { FormField, FormItem, FormLabel, FormControl, FormDescription, FormMessage } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Combobox } from '@/components/ui/combobox';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';
import { Label } from '@/components/ui/label';
import { getModels, getProviders } from '@/services/providerApi';
import type { AIModel, AIProvider } from '@/types/agent.types';
import type { KnowledgeSourceFormValues } from '../types';
import { CreateSourceAdvanced } from './CreateSourceAdvanced';
import { dimensionForModel, isSmartSearch, looksLikeEmbeddingModel } from './createSourceHelpers';

const SMART_DEFAULT_TYPE = 'zvec';
const STANDARD_TYPE = 'sqlite_fts';

export function CreateSourceStepName() {
  const form = useFormContext<KnowledgeSourceFormValues>();
  const type = form.watch('knowledge_type');
  const model = form.watch('embedding_model');
  const provider = form.watch('embedding_provider');
  const smart = isSmartSearch(type);
  const [providers, setProviders] = useState<AIProvider[]>([]);
  const [models, setModels] = useState<AIModel[]>([]);

  useEffect(() => {
    if (!smart || providers.length > 0) return;
    getProviders()
      .then((d) => setProviders(d as AIProvider[]))
      .catch(() => setProviders([]));
    getModels()
      .then(setModels)
      .catch(() => setModels([]));
  }, [smart, providers.length]);

  const providerOptions = useMemo(
    () => providers.map((p) => ({ value: p.name, label: p.provider_name || p.name })),
    [providers],
  );
  const modelOptions = useMemo(() => {
    const scoped = provider ? models.filter((m) => m.provider === provider) : models;
    const embed = scoped.filter((m) => looksLikeEmbeddingModel(m.model_name));
    return (embed.length > 0 ? embed : scoped).map((m) => ({
      value: m.model_name,
      label: m.model_name,
      subtitle: m.provider,
    }));
  }, [models, provider]);

  const setQuality = (value: string) => {
    if (value === 'smart') {
      if (!isSmartSearch(type)) form.setValue('knowledge_type', SMART_DEFAULT_TYPE, { shouldValidate: true });
    } else {
      form.setValue('knowledge_type', STANDARD_TYPE, { shouldValidate: true });
    }
  };

  const pickModel = (value: string) => {
    form.setValue('embedding_model', value, { shouldValidate: true, shouldDirty: true });
    const picked = models.find((m) => m.model_name === value);
    if (picked?.provider && !provider) form.setValue('embedding_provider', picked.provider, { shouldValidate: true });
    const dim = dimensionForModel(value);
    if (dim) form.setValue('vector_dimension', dim, { shouldValidate: true });
  };

  return (
    <div className="space-y-5">
      <FormField
        control={form.control}
        name="source_name"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Name</FormLabel>
            <FormControl>
              <Input placeholder="e.g. Product handbook" autoFocus {...field} />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />
      <FormField
        control={form.control}
        name="description"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Description (optional)</FormLabel>
            <FormControl>
              <Textarea rows={2} placeholder="What knowledge does this hold?" {...field} value={field.value ?? ''} />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />
      <div className="space-y-2">
        <Label>Search quality</Label>
        <RadioGroup value={smart ? 'smart' : 'standard'} onValueChange={setQuality} className="gap-2">
          {[
            { v: 'standard', t: 'Standard keyword search', d: 'Works instantly, no setup' },
            { v: 'smart', t: 'Smart (meaning-based) search', d: 'Understands questions, not just words. Needs an AI provider' },
          ].map((o) => (
            <Label
              key={o.v}
              htmlFor={`quality-${o.v}`}
              className="flex cursor-pointer items-start gap-3 rounded-md border p-3 font-normal"
            >
              <RadioGroupItem id={`quality-${o.v}`} value={o.v} className="mt-1" />
              <span>
                <span className="block text-sm font-medium">{o.t}</span>
                <span className="block text-sm text-steel">{o.d}</span>
              </span>
            </Label>
          ))}
        </RadioGroup>
      </div>
      {smart && (
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField
            control={form.control}
            name="embedding_provider"
            render={({ field }) => (
              <FormItem>
                <FormLabel>AI provider</FormLabel>
                <FormControl>
                  <Combobox
                    options={providerOptions}
                    value={field.value ?? ''}
                    onValueChange={field.onChange}
                    placeholder="Select AI provider..."
                    emptyText="No providers found."
                  />
                </FormControl>
              </FormItem>
            )}
          />
          <FormItem>
            <FormLabel>Smart search model</FormLabel>
            <Combobox
              options={modelOptions}
              value={model ?? ''}
              onValueChange={pickModel}
              placeholder="Select a model..."
              searchPlaceholder="Search models..."
              emptyText="No models found. Type one under Advanced options."
            />
            <FormDescription>Used to understand the meaning of your documents.</FormDescription>
            {form.formState.errors.embedding_model && (
              <p className="text-sm text-destructive">Choose a model for smart search</p>
            )}
          </FormItem>
        </div>
      )}
      <Accordion type="single" collapsible>
        <AccordionItem value="advanced" className="border-b-0">
          <AccordionTrigger className="text-sm">Advanced options</AccordionTrigger>
          <AccordionContent>
            <CreateSourceAdvanced />
          </AccordionContent>
        </AccordionItem>
      </Accordion>
    </div>
  );
}
