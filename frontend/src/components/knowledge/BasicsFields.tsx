import { UseFormReturn } from 'react-hook-form';
import { FormField, FormItem, FormLabel, FormControl, FormDescription, FormMessage } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import type { KnowledgeSourceFormValues } from './types';

interface BasicsFieldsProps {
  form: UseFormReturn<KnowledgeSourceFormValues>;
  /** Show the name field (stored as source_name; the document id never changes). */
  showName?: boolean;
  /** Show the on/off switch. */
  showDisabled?: boolean;
}

/** Name, description and the on/off switch. */
export function BasicsFields({ form, showName, showDisabled }: BasicsFieldsProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Details</CardTitle>
        <CardDescription>Name and description for this knowledge source</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-6">
        {showName && (
          <FormField
            control={form.control}
            name="source_name"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Name</FormLabel>
                <FormControl>
                  <Input placeholder="e.g. Product documentation" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        )}
        <FormField
          control={form.control}
          name="description"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Description</FormLabel>
              <FormControl>
                <Textarea placeholder="What this knowledge source contains" className="min-h-[80px] resize-y" {...field} />
              </FormControl>
              <FormDescription>Helps you and your team remember what is inside.</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
        {showDisabled && (
          <FormField
            control={form.control}
            name="disabled"
            render={({ field }) => (
              <FormItem className="flex items-center justify-between gap-4 rounded-md border p-3">
                <div className="space-y-0.5">
                  <FormLabel>Available to agents</FormLabel>
                  <FormDescription>When on, agents you attach this source to can search it. Turn it off to pause it without deleting anything.</FormDescription>
                </div>
                <FormControl>
                  <Switch checked={!field.value} onCheckedChange={(on) => field.onChange(!on)} data-testid="available-to-agents" />
                </FormControl>
              </FormItem>
            )}
          />
        )}
      </CardContent>
    </Card>
  );
}
