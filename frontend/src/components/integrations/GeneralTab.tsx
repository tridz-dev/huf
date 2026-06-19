import type { UseFormReturn } from 'react-hook-form';
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Switch } from '@/components/ui/switch';
import { Input } from '@/components/ui/input';
import type { IntegrationFormValues } from './types';

interface GeneralTabProps {
  form: UseFormReturn<IntegrationFormValues>;
  isNew: boolean;
  serviceLabel?: string;
  lastUsed?: string;
  lastError?: string;
}

export function GeneralTab({
  form,
  isNew,
  serviceLabel,
  lastUsed,
  lastError,
}: GeneralTabProps) {
  return (
    <div className="space-y-6 rounded-lg border p-6">
      <FormField
        control={form.control}
        name="service"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Integration Service</FormLabel>
            <FormControl>
              <Input
                {...field}
                readOnly
                className="capitalize bg-muted"
                value={serviceLabel || field.value.replace(/_/g, ' ')}
              />
            </FormControl>
            {!isNew && (
              <FormDescription>Service cannot be changed after creation.</FormDescription>
            )}
            <FormMessage />
          </FormItem>
        )}
      />

      <FormField
        control={form.control}
        name="is_active"
        render={({ field }) => (
          <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
            <div className="space-y-0.5">
              <FormLabel>Active</FormLabel>
              <FormDescription>
                Inactive integrations are ignored when agents resolve credentials.
              </FormDescription>
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
          <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
            <div className="space-y-0.5">
              <FormLabel>Default for this service</FormLabel>
              <FormDescription>
                When multiple configs exist for the same service, the default is preferred.
              </FormDescription>
            </div>
            <FormControl>
              <Switch checked={field.value} onCheckedChange={field.onChange} />
            </FormControl>
          </FormItem>
        )}
      />

      {!isNew && (lastUsed || lastError) && (
        <div className="space-y-3 rounded-lg border p-4 bg-muted/30">
          <h3 className="text-sm font-medium">Usage Statistics</h3>
          {lastUsed && (
            <p className="text-sm text-muted-foreground">Last used: {new Date(lastUsed).toLocaleString()}</p>
          )}
          {lastError && (
            <p className="text-sm text-destructive">Last error: {lastError}</p>
          )}
        </div>
      )}
    </div>
  );
}
