import type { UseFormReturn } from 'react-hook-form';
import { FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import type { CredentialSchemaItem } from '@/types/integration.types';
import type { IntegrationFormValues } from '../types';

interface CredentialsSectionProps {
  form: UseFormReturn<IntegrationFormValues>;
  schema: CredentialSchemaItem[];
  isNew: boolean;
  /** Credential keys that already have a value stored (the value itself is never sent to the page). */
  savedKeys: Set<string>;
}

/** Name and credentials: the first thing on the page, so nobody has to find them. */
export function CredentialsSection({ form, schema, isNew, savedKeys }: CredentialsSectionProps) {
  return (
    <section className="space-y-4 rounded-lg border p-5" id="integration-credentials" data-testid="integration-credentials">
      <FormField
        control={form.control}
        name="display_label"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Name</FormLabel>
            <FormControl>
              <Input {...field} value={field.value ?? ''} maxLength={80} placeholder="Optional, for example Marketing Slack" data-testid="integration-name-input" />
            </FormControl>
            <FormDescription>Shown in lists and when you pick this connection. Leave empty to use the service and account.</FormDescription>
            <FormMessage />
          </FormItem>
        )}
      />

      {schema.length === 0 ? (
        <p className="text-sm text-muted-foreground">This service needs no credentials.</p>
      ) : (
        <>
          <div>
            <h2 className="text-sm font-medium">Credentials</h2>
            {!isNew && (
              <p className="text-sm text-muted-foreground">
                Saved values stay hidden. Leave a field empty to keep what is saved, or type to replace it.
              </p>
            )}
          </div>
          {schema.map((item) => {
            const saved = savedKeys.has(item.key);
            return (
              <FormField
                key={item.key}
                control={form.control}
                name={`credentialValues.${item.key}`}
                render={({ field }) => (
                  <FormItem>
                    <div className="flex flex-wrap items-center gap-2">
                      <FormLabel>
                        {item.label}
                        {item.required && <span className="ml-1 text-destructive">*</span>}
                      </FormLabel>
                      {!isNew && (
                        <Badge variant={saved ? 'pill-success' : 'pill-neutral'} data-testid={`credential-state-${item.key}`}>
                          {saved ? 'Saved' : 'Not set'}
                        </Badge>
                      )}
                    </div>
                    <FormControl>
                      <Input
                        {...field}
                        type={item.secret === false ? 'text' : 'password'}
                        autoComplete="off"
                        placeholder={saved ? 'Saved. Type to replace it' : `Enter ${item.label.toLowerCase()}`}
                        value={field.value ?? ''}
                        data-testid={`credential-input-${item.key}`}
                      />
                    </FormControl>
                    {item.description && <FormDescription>{item.description}</FormDescription>}
                    <FormMessage />
                  </FormItem>
                )}
              />
            );
          })}
        </>
      )}
    </section>
  );
}
