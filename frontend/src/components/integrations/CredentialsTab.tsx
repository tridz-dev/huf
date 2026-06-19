import type { UseFormReturn } from 'react-hook-form';
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import type { CredentialSchemaItem } from '@/types/integration.types';
import type { IntegrationFormValues } from './types';

interface CredentialsTabProps {
  form: UseFormReturn<IntegrationFormValues>;
  schema: CredentialSchemaItem[];
  isNew: boolean;
}

export function CredentialsTab({ form, schema, isNew }: CredentialsTabProps) {
  if (schema.length === 0) {
    return (
      <div className="rounded-lg border p-6 text-sm text-muted-foreground">
        No credential schema defined for this service.
      </div>
    );
  }

  return (
    <div className="space-y-4 rounded-lg border p-6">
      {!isNew && (
        <p className="text-sm text-muted-foreground">
          Leave credential fields blank to keep existing values unchanged.
        </p>
      )}
      {schema.map((item) => (
        <FormField
          key={item.key}
          control={form.control}
          name={`credentialValues.${item.key}`}
          render={({ field }) => (
            <FormItem>
              <FormLabel>
                {item.label}
                {item.required && <span className="text-destructive ml-1">*</span>}
              </FormLabel>
              <FormControl>
                <Input
                  {...field}
                  type="password"
                  autoComplete="off"
                  placeholder={isNew ? `Enter ${item.label.toLowerCase()}` : '••••••••'}
                  value={field.value ?? ''}
                />
              </FormControl>
              {item.description && <FormDescription>{item.description}</FormDescription>}
              <FormMessage />
            </FormItem>
          )}
        />
      ))}
    </div>
  );
}
