import { UseFormReturn } from 'react-hook-form';
import { FormField, FormItem, FormLabel, FormControl, FormDescription } from '@/components/ui/form';
import { Switch } from '@/components/ui/switch';
import type { MemoryPolicyFormValues } from './memoryPolicyFormSchema';

export function SwitchField({
  form,
  name,
  label,
  description,
}: {
  form: UseFormReturn<MemoryPolicyFormValues>;
  name: 'enabled' | 'approval_required' | 'allow_agent_write' | 'allow_user_scope_write' |
    'allow_role_scope_write' | 'allow_agent_scope_write' | 'allow_site_scope_write' |
    'auto_promote_to_knowledge';
  label: string;
  description: string;
}) {
  return (
    <FormField
      control={form.control}
      name={name}
      render={({ field }) => (
        <FormItem className="flex flex-row items-center justify-between rounded-none border p-4">
          <div className="space-y-0.5 pr-4">
            <FormLabel className="text-base">{label}</FormLabel>
            <FormDescription>{description}</FormDescription>
          </div>
          <FormControl>
            <Switch checked={field.value ?? false} onCheckedChange={field.onChange} />
          </FormControl>
        </FormItem>
      )}
    />
  );
}
