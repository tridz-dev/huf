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
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { integrationCategories } from '@/data/integrations';
import type { IntegrationServiceFormValues } from './types';

interface GeneralTabProps {
  form: UseFormReturn<IntegrationServiceFormValues>;
  isNew: boolean;
}

export function GeneralTab({ form, isNew }: GeneralTabProps) {
  return (
    <div className="space-y-6 rounded-lg border p-6">
      <FormField
        control={form.control}
        name="service_name"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Service Name</FormLabel>
            <FormControl>
              <Input
                {...field}
                readOnly={!isNew}
                className={!isNew ? 'bg-muted' : undefined}
                placeholder="e.g. my_custom_api"
              />
            </FormControl>
            <FormDescription>
              {isNew
                ? 'Unique identifier used as the document name and Integration Settings link target.'
                : 'Service name cannot be changed after creation.'}
            </FormDescription>
            <FormMessage />
          </FormItem>
        )}
      />

      <FormField
        control={form.control}
        name="category"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Category</FormLabel>
            <Select value={field.value} onValueChange={field.onChange}>
              <FormControl>
                <SelectTrigger>
                  <SelectValue placeholder="Select category" />
                </SelectTrigger>
              </FormControl>
              <SelectContent>
                {integrationCategories.map((category) => (
                  <SelectItem key={category} value={category}>
                    {category}
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
        name="description"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Description</FormLabel>
            <FormControl>
              <Textarea
                {...field}
                value={field.value ?? ''}
                placeholder="Brief description of what this integration provides"
                rows={3}
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />

      <FormField
        control={form.control}
        name="documentation_url"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Documentation URL</FormLabel>
            <FormControl>
              <Input
                {...field}
                value={field.value ?? ''}
                placeholder="https://docs.example.com/setup"
              />
            </FormControl>
            <FormDescription>Optional link shown in the service catalog.</FormDescription>
            <FormMessage />
          </FormItem>
        )}
      />
    </div>
  );
}
