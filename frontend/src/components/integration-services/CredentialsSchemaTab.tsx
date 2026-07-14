import { Plus } from 'lucide-react';
import type { UseFormReturn } from 'react-hook-form';
import { Button } from '@/components/ui/button';
import { FormMessage } from '@/components/ui/form';
import { CredentialSchemaCard } from './CredentialSchemaCard';
import type { IntegrationServiceFormValues } from './types';

interface CredentialsSchemaTabProps {
  form: UseFormReturn<IntegrationServiceFormValues>;
}

export function CredentialsSchemaTab({ form }: CredentialsSchemaTabProps) {
  const credentials = form.watch('required_credentials');

  const handleChange = (index: number, data: Partial<IntegrationServiceFormValues['required_credentials'][number]>) => {
    const next = [...credentials];
    next[index] = { ...next[index], ...data };
    form.setValue('required_credentials', next, { shouldDirty: true, shouldValidate: true });
  };

  const handleDelete = (index: number) => {
    const next = credentials.filter((_, i) => i !== index);
    form.setValue('required_credentials', next, { shouldDirty: true, shouldValidate: true });
  };

  const handleAdd = () => {
    form.setValue(
      'required_credentials',
      [
        ...credentials,
        {
          key: '',
          label: '',
          required: true,
          description: '',
        },
      ],
      { shouldDirty: true, shouldValidate: true },
    );
  };

  return (
    <div className="space-y-4">
      <div className="rounded-lg border p-4 bg-muted/30">
        <p className="text-sm text-muted-foreground">
          Define the credential fields required when users configure Integration Settings for this
          service. Keys are used internally; labels are shown in the form.
        </p>
      </div>

      <div className="space-y-4">
        {credentials.map((item, index) => (
          <CredentialSchemaCard
            key={`credential-${index}`}
            item={item}
            index={index}
            onChange={handleChange}
            onDelete={handleDelete}
            canDelete={credentials.length > 1}
          />
        ))}
      </div>

      <Button type="button" variant="outline" onClick={handleAdd}>
        <Plus className="w-4 h-4 mr-2" />
        Add Credential Field
      </Button>

      <FormMessage>{form.formState.errors.required_credentials?.message}</FormMessage>
    </div>
  );
}
