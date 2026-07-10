import { Plus, Trash2 } from 'lucide-react';
import type { UseFormReturn } from 'react-hook-form';
import { useFieldArray } from 'react-hook-form';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import type { IntegrationFormValues } from './types';

interface RecipientsTabProps {
  form: UseFormReturn<IntegrationFormValues>;
}

export function RecipientsTab({ form }: RecipientsTabProps) {
  const { fields, append, remove } = useFieldArray({
    control: form.control,
    name: 'recipients',
  });

  return (
    <div className="space-y-4 rounded-lg border p-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-medium">Named Recipients</h3>
          <p className="text-sm text-muted-foreground mt-1">
            Define named recipients for this service. The agent can look up a recipient by name and get their service-specific ID (e.g. Telegram Chat ID, Slack User ID, Discord Channel ID).
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() =>
            append({ recipient_name: '', recipient_id: '', user: '' })
          }
        >
          <Plus className="w-4 h-4 mr-2" />
          Add Recipient
        </Button>
      </div>

      {fields.length === 0 ? (
        <p className="text-sm text-muted-foreground text-center py-8">
          No recipients configured. Add one so agents can look up IDs by name.
        </p>
      ) : (
        <div className="space-y-4">
          {fields.map((field, index) => (
            <div key={field.id} className="grid gap-4 rounded-lg border p-4 md:grid-cols-[1fr_1fr_1fr_auto]">
              <FormField
                control={form.control}
                name={`recipients.${index}.recipient_name`}
                render={({ field: f }) => (
                  <FormItem>
                    <FormLabel>Name</FormLabel>
                    <FormControl>
                      <Input {...f} placeholder="e.g. Sales Alerts" />
                    </FormControl>
                    <FormDescription>
                      A human-friendly label for this recipient (e.g. John Doe, Sales Alerts, Engineering Team)
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name={`recipients.${index}.recipient_id`}
                render={({ field: f }) => (
                  <FormItem>
                    <FormLabel>Recipient ID</FormLabel>
                    <FormControl>
                      <Input {...f} placeholder="Service-specific ID" />
                    </FormControl>
                    <FormDescription>
                      Service-specific ID: Telegram Chat ID, Slack User/Channel ID, Discord Channel ID, email address, etc.
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name={`recipients.${index}.user`}
                render={({ field: f }) => (
                  <FormItem>
                    <FormLabel>User (optional)</FormLabel>
                    <FormControl>
                      <Input {...f} placeholder="Frappe user email" />
                    </FormControl>
                    <FormDescription>Optionally link to a Frappe User account</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <div className="flex items-end">
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  onClick={() => remove(index)}
                  className="text-destructive hover:text-destructive"
                >
                  <Trash2 className="w-4 h-4" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
