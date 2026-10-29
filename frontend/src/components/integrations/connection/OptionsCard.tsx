import type { UseFormReturn } from 'react-hook-form';
import { FormControl, FormDescription, FormField, FormItem, FormLabel } from '@/components/ui/form';
import { Switch } from '@/components/ui/switch';
import type { IntegrationFormValues } from '../types';

/** The two switches most people never touch, in plain words. */
export function OptionsCard({ form }: { form: UseFormReturn<IntegrationFormValues> }) {
  return (
    <section className="space-y-3 rounded-lg border p-5" data-testid="integration-options">
      <h2 className="text-sm font-medium">Options</h2>
      <FormField
        control={form.control}
        name="is_active"
        render={({ field }) => (
          <FormItem className="flex flex-row items-center justify-between gap-4 rounded-lg border p-4">
            <div className="space-y-0.5">
              <FormLabel>Active</FormLabel>
              <FormDescription>Turn off to pause this connection without deleting it.</FormDescription>
            </div>
            <FormControl>
              <Switch checked={field.value} onCheckedChange={field.onChange} />
            </FormControl>
          </FormItem>
        )}
      />
      <FormField
        control={form.control}
        name="is_default"
        render={({ field }) => (
          <FormItem className="flex flex-row items-center justify-between gap-4 rounded-lg border p-4">
            <div className="space-y-0.5">
              <FormLabel>Use by default</FormLabel>
              <FormDescription>Used automatically when a step or agent does not choose a specific account.</FormDescription>
            </div>
            <FormControl>
              <Switch checked={field.value} onCheckedChange={field.onChange} />
            </FormControl>
          </FormItem>
        )}
      />
    </section>
  );
}
