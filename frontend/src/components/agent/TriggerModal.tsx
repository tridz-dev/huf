import React from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Button } from '@/components/ui/button';
import { TriggerFieldsRenderer } from './TriggerFieldsRenderer';
import { triggerFieldsConfig } from './TriggerFieldsConfig';
import type { AgentTriggerDoc, TriggerTypeOption } from '@/services/agentApi';
import type { TriggerType } from '@/types/agent.types';

/**
 * Dynamically validate trigger fields based on triggerFieldsConfig
 * This ensures validation rules stay in sync with the field configuration
 */
function validateTriggerFields(data: any): { valid: boolean; missingFields: string[] } {
  const triggerType = data.trigger_type;
  if (!triggerType || !triggerFieldsConfig[triggerType]) {
    return { valid: true, missingFields: [] }; // Unknown trigger type, skip validation
  }

  const fields = triggerFieldsConfig[triggerType];
  const requiredFields = fields.filter(
    (field) => field.required && field.type !== 'custom' // Skip custom fields (they're display-only)
  );

  // Check if all required fields have values
  const missingFields: string[] = [];
  for (const field of requiredFields) {
    const value = data[field.field];
    if (!value || (typeof value === 'string' && value.trim() === '')) {
      missingFields.push(field.label);
    }
  }

  return {
    valid: missingFields.length === 0,
    missingFields,
  };
}

const triggerFormSchema = z.object({
  trigger_name: z.string().min(1, 'Trigger name is required').optional(),
  trigger_type: z.enum(['Schedule', 'Doc Event', 'Webhook', 'App Event', 'Manual']),
  active: z.boolean(),
  scheduled_interval: z.string().optional(),
  interval_count: z.string()
    .optional()
    .refine(
      (val) => {
        if (!val || val.trim() === '') return true; // Allow empty
        return /^\d+$/.test(val) && parseInt(val, 10) > 0; // Must be positive integer
      },
      { message: 'Interval count must be a positive whole number' }
    ),
  reference_doctype: z.string().optional(),
  doc_event: z.string().optional(),
  condition: z.string().optional(),
  app_name: z.string().optional(),
  event_name: z.string().optional(),
}).refine(
  (data) => validateTriggerFields(data).valid,
  (data) => {
    const validation = validateTriggerFields(data);
    return {
      message: validation.missingFields.length > 0
        ? `Please fill in: ${validation.missingFields.join(', ')}`
        : "Required fields missing for selected trigger type",
      path: ['trigger_type'], // Show error on trigger_type field
    };
  }
);

type TriggerFormValues = z.infer<typeof triggerFormSchema>;

interface TriggerModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  editingTrigger: AgentTriggerDoc | null;
  triggerTypes: TriggerTypeOption[];
  docTypes: Array<{ name: string }>;
  loadingDocTypes: boolean;
  agentId?: string;
  onSave: (values: TriggerFormValues) => Promise<void>;
}

export function TriggerModal({
  open,
  onOpenChange,
  editingTrigger,
  triggerTypes,
  docTypes,
  loadingDocTypes,
  agentId,
  onSave,
}: TriggerModalProps) {
  const triggerForm = useForm<TriggerFormValues>({
    resolver: zodResolver(triggerFormSchema),
    defaultValues: {
      trigger_name: '',
      trigger_type: 'Schedule',
      active: true,
      interval_count: undefined,
    },
  });

  const watchTriggerType = triggerForm.watch('trigger_type');

  // Reset form when modal opens/closes or editing trigger changes
  React.useEffect(() => {
    if (open) {
      if (editingTrigger) {
        triggerForm.reset({
          trigger_name: editingTrigger.trigger_name,
          trigger_type: (editingTrigger.trigger_type || 'Schedule') as TriggerType,
          active: editingTrigger.disabled === 0 || editingTrigger.disabled === undefined,
          scheduled_interval: editingTrigger.scheduled_interval,
          interval_count: editingTrigger.interval_count?.toString() || undefined,
          reference_doctype: editingTrigger.reference_doctype,
          doc_event: editingTrigger.doc_event,
          condition: editingTrigger.condition,
        });
      } else {
        triggerForm.reset({
          trigger_name: '',
          trigger_type: 'Schedule',
          active: true,
          interval_count: undefined,
          scheduled_interval: undefined,
          reference_doctype: undefined,
          doc_event: undefined,
          condition: undefined,
        });
      }
    }
  }, [open, editingTrigger, triggerForm]);

  const handleSubmit = async (values: TriggerFormValues) => {
    console.log('handleSubmit', values);
    await onSave(values);
  };

  // Add error handler to see validation errors
  const handleFormError = (errors: any) => {
    console.error('Form validation errors:', errors);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[600px]">
        <DialogHeader>
          <DialogTitle>Configure Trigger</DialogTitle>
          <DialogDescription>
            {editingTrigger ? 'Edit trigger configuration' : 'Add a new trigger to this agent'}
          </DialogDescription>
        </DialogHeader>
        <Form {...triggerForm}>
          <form onSubmit={triggerForm.handleSubmit(handleSubmit, handleFormError)} className="space-y-4">
            {/* Trigger Name Field - Only editable when adding */}
            {!editingTrigger && (
              <FormField
                control={triggerForm.control}
                name="trigger_name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Trigger Name</FormLabel>
                    <FormControl>
                      <Input placeholder="Enter trigger name" {...field} />
                    </FormControl>
                    <FormDescription>A unique name for this trigger</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            )}

            {/* Trigger Name Display - Read-only when editing */}
            {editingTrigger && (
              <FormItem>
                <FormLabel>Trigger Name</FormLabel>
                <FormControl>
                  <Input value={editingTrigger.trigger_name} disabled />
                </FormControl>
                <FormDescription>Trigger name cannot be changed after creation</FormDescription>
              </FormItem>
            )}

            <FormField
              control={triggerForm.control}
              name="trigger_type"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Trigger Type</FormLabel>
                  <Select onValueChange={field.onChange} value={field.value}>
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {Array.isArray(triggerTypes) && triggerTypes.map((type) => (
                        <SelectItem key={type.name} value={type.name}>
                          {type.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={triggerForm.control}
              name="active"
              render={({ field }) => (
                <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                  <div className="space-y-0.5">
                    <FormLabel className="text-base">Active</FormLabel>
                    <FormDescription>Enable this trigger</FormDescription>
                  </div>
                  <FormControl>
                    <Switch checked={field.value} onCheckedChange={field.onChange} />
                  </FormControl>
                </FormItem>
              )}
            />

            {/* Render trigger fields based on configuration */}
            {watchTriggerType && (
              <TriggerFieldsRenderer
                triggerType={watchTriggerType}
                control={triggerForm.control}
                docTypes={docTypes}
                loadingDocTypes={loadingDocTypes}
                agentId={agentId}
              />
            )}

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit">
                {editingTrigger ? 'Update' : 'Add'} Trigger
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}

