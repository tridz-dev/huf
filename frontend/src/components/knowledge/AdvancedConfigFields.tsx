import { useEffect, useState } from 'react';
import { useFormContext, useWatch } from 'react-hook-form';
import { FormField, FormItem, FormLabel, FormControl, FormDescription, FormMessage } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { getAdvancedConfigSchema, type AdvancedConfigSchemaEntry } from '@/services/knowledgeApi';
import type { KnowledgeSourceFormValues } from './types';

interface AdvancedConfigFieldsProps {
  knowledgeType: string;
}

export function AdvancedConfigFields({ knowledgeType }: AdvancedConfigFieldsProps) {
  const { control, setValue, getValues } = useFormContext<KnowledgeSourceFormValues>();
  const [schema, setSchema] = useState<AdvancedConfigSchemaEntry[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getAdvancedConfigSchema(knowledgeType)
      .then((entries) => {
        if (cancelled) return;
        setSchema(entries || []);
      })
      .catch(() => {
        if (cancelled) return;
        setSchema([]);
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [knowledgeType]);

  // Ensure defaults are present in form state when schema loads.
  useEffect(() => {
    const current = getValues('advanced_config') || {};
    const updates: Record<string, unknown> = {};
    for (const entry of schema) {
      if (entry.key in current) continue;
      updates[entry.key] = entry.default;
    }
    if (Object.keys(updates).length > 0) {
      setValue('advanced_config', { ...current, ...updates }, { shouldDirty: false });
    }
  }, [schema, getValues, setValue]);

  if (loading || schema.length === 0) {
    return null;
  }

  return (
    <div className="grid gap-6 sm:grid-cols-2">
      {schema.map((entry) => (
        <SchemaField key={entry.key} entry={entry} control={control} />
      ))}
    </div>
  );
}

interface SchemaFieldProps {
  entry: AdvancedConfigSchemaEntry;
  control: ReturnType<typeof useFormContext<KnowledgeSourceFormValues>>['control'];
}

function SchemaField({ entry, control }: SchemaFieldProps) {
  const watchedValues = useWatch({ control });
  const { setValue } = useFormContext<KnowledgeSourceFormValues>();

  if (entry.visible_when) {
    const hidden = Object.entries(entry.visible_when).some(([field, expected]) => {
      const actual = watchedValues[field as keyof KnowledgeSourceFormValues];
      return actual !== expected;
    });
    if (hidden) return null;
  }

  const fieldName = `advanced_config.${entry.key}` as `advanced_config.${string}`;

  switch (entry.type) {
    case 'boolean':
      return (
        <FormField
          control={control}
          name={fieldName}
          render={({ field }) => (
            <FormItem className="flex flex-row items-start space-x-3 space-y-0 sm:col-span-2">
              <FormControl>
                <Checkbox checked={Boolean(field.value)} onCheckedChange={field.onChange} />
              </FormControl>
              <div className="space-y-1 leading-none">
                <FormLabel>{entry.label}</FormLabel>
                {entry.help_text && <FormDescription>{entry.help_text}</FormDescription>}
              </div>
            </FormItem>
          )}
        />
      );

    case 'select':
      return (
        <FormField
          control={control}
          name={fieldName}
          render={({ field }) => (
            <FormItem>
              <FormLabel>{entry.label}</FormLabel>
              <Select onValueChange={field.onChange} value={String(field.value ?? entry.default ?? '')}>
                <FormControl>
                  <SelectTrigger>
                    <SelectValue placeholder={`Select ${entry.label.toLowerCase()}`} />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  {entry.options?.map((option) => (
                    <SelectItem key={option} value={option}>
                      {option}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {entry.help_text && <FormDescription>{entry.help_text}</FormDescription>}
              <FormMessage />
            </FormItem>
          )}
        />
      );

    case 'number':
      return (
        <FormField
          control={control}
          name={fieldName}
          render={({ field }) => (
            <FormItem>
              <FormLabel>{entry.label}</FormLabel>
              <FormControl>
                <Input
                  type="number"
                  min={entry.min}
                  max={entry.max}
                  value={String(field.value ?? entry.default ?? '')}
                  onChange={(e) => {
                    const raw = e.target.value;
                    const num = raw === '' ? undefined : Number(raw);
                    setValue(fieldName, num, { shouldValidate: true });
                  }}
                />
              </FormControl>
              {entry.help_text && <FormDescription>{entry.help_text}</FormDescription>}
              <FormMessage />
            </FormItem>
          )}
        />
      );

    case 'text':
    default:
      return (
        <FormField
          control={control}
          name={fieldName}
          render={({ field }) => (
            <FormItem>
              <FormLabel>{entry.label}</FormLabel>
              <FormControl>
                <Input {...field} value={String(field.value ?? entry.default ?? '')} />
              </FormControl>
              {entry.help_text && <FormDescription>{entry.help_text}</FormDescription>}
              <FormMessage />
            </FormItem>
          )}
        />
      );
  }
}
