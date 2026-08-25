import React from 'react';
import { useForm, Control } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { ArrowLeft, Loader2 } from 'lucide-react';
import {
  Dialog,
  DialogDescription,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  DialogScrollBody,
  DialogScrollContent,
  DialogScrollFooter,
  DialogScrollHeader,
} from '@/components/ui/dialog-scroll';
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
import { toast } from 'sonner';
import { TriggerFieldsRenderer } from './TriggerFieldsRenderer';
import { triggerFieldsConfig } from './TriggerFieldsConfig';
import { TriggerDocEventExtras } from './TriggerDocEventExtras';
import { TriggerScheduleExtras } from './TriggerScheduleExtras';
import { AppPicker } from '@/components/capabilities/AppPicker';
import { ResourceCard } from '@/components/capabilities/ResourceCard';
import { ResourceDetail } from '@/components/capabilities/ResourceDetail';
import { EventDetail } from '@/components/capabilities/EventDetail';
import { getAppResources } from '@/services/capabilityApi';
import type { AgentTriggerDoc, TriggerTypeOption } from '@/services/agentApi';
import type { TriggerType } from '@/types/agent.types';
import type { CapabilityApp, CapabilityDescriptor } from '@/types/capability.types';

/**
 * Steps for the guided "From App" Doc Event trigger creation path (plan §14.3).
 * "form" is the existing raw DocType + doc_event Advanced path; it stays the
 * default/fallback for every trigger type (Schedule/Webhook/App Event/Manual
 * always render "form" since only Doc Event has a guided entry point).
 */
type FromAppStep = 'form' | 'app' | 'resource' | 'resource-detail' | 'event';

/** Shape returned by huf.ai.capability_discovery.api.get_app_resources, matching ResourceCard's props. */
interface AppResourceSummary {
  doctype: string;
  title: string;
  visibility: string;
  is_exposed?: boolean;
  submittable?: boolean;
}

/**
 * Dynamically validate trigger fields based on triggerFieldsConfig
 * This ensures validation rules stay in sync with the field configuration
 */
function validateTriggerFields(data: Record<string, unknown>): { valid: boolean; missingFields: string[] } {
  const triggerType = typeof data.trigger_type === 'string' ? data.trigger_type : undefined;
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
  execution_mode: z.enum(['Realtime', 'Batch']).optional(),
  reference_doctype: z.string().optional(),
  doc_event: z.string().optional(),
  condition: z.string().optional(),
  prompt_field: z.string().optional(),
  file_attachments: z
    .array(
      z.object({
        name: z.string().optional(),
        source_type: z.enum(['DocField', 'Child Table Field']),
        field_name: z.string().min(1, 'Attach field name is required'),
        child_table: z.string().optional(),
      }).refine(
        (row) => row.source_type !== 'Child Table Field' || !!row.child_table,
        { message: 'Child table is required', path: ['child_table'] }
      )
    )
    .optional(),
  app_name: z.string().optional(),
  event_name: z.string().optional(),
  webhook_slug: z.string().optional(),
  webhook_key: z.string().optional(),
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
      execution_mode: 'Realtime',
      file_attachments: [],
    },
  });

  const watchTriggerType = triggerForm.watch('trigger_type');

  // "From App" guided Doc Event creation wizard state (local component state,
  // matching how the rest of this modal manages state). Only ever entered for
  // new triggers; the raw Advanced form above is untouched and remains the
  // fallback for every trigger type.
  const [fromAppStep, setFromAppStep] = React.useState<FromAppStep>('form');
  const [selectedApp, setSelectedApp] = React.useState<CapabilityApp | null>(null);
  const [selectedDoctype, setSelectedDoctype] = React.useState<string | null>(null);
  const [selectedEventCapability, setSelectedEventCapability] =
    React.useState<CapabilityDescriptor | null>(null);
  const [appResources, setAppResources] = React.useState<AppResourceSummary[]>([]);
  const [loadingAppResources, setLoadingAppResources] = React.useState(false);

  const resetFromAppWizard = () => {
    setFromAppStep('form');
    setSelectedApp(null);
    setSelectedDoctype(null);
    setSelectedEventCapability(null);
    setAppResources([]);
  };

  // Reset form when modal opens/closes or editing trigger changes
  React.useEffect(() => {
    if (open) {
      resetFromAppWizard();
      if (editingTrigger) {
        triggerForm.reset({
          trigger_name: editingTrigger.trigger_name,
          trigger_type: (editingTrigger.trigger_type || 'Schedule') as TriggerType,
          active: editingTrigger.disabled === 0 || editingTrigger.disabled === undefined,
          scheduled_interval: editingTrigger.scheduled_interval,
          interval_count: editingTrigger.interval_count?.toString() || undefined,
          execution_mode: (editingTrigger.execution_mode as 'Realtime' | 'Batch') || 'Realtime',
          reference_doctype: editingTrigger.reference_doctype,
          doc_event: editingTrigger.doc_event,
          condition: editingTrigger.condition,
          prompt_field: editingTrigger.prompt_field,
          file_attachments: editingTrigger.file_attachments || [],
          app_name: editingTrigger.app_name,
          event_name: editingTrigger.event_name,
          webhook_slug: editingTrigger.webhook_slug,
          webhook_key: editingTrigger.webhook_key,
        });
      } else {
        triggerForm.reset({
          trigger_name: '',
          trigger_type: 'Schedule',
          active: true,
          interval_count: undefined,
          scheduled_interval: undefined,
          execution_mode: 'Realtime',
          reference_doctype: undefined,
          doc_event: undefined,
          condition: undefined,
          prompt_field: undefined,
          file_attachments: [],
          app_name: undefined,
          event_name: undefined,
          webhook_slug: undefined,
          webhook_key: undefined,
        });
      }
    }
  }, [open, editingTrigger, triggerForm]);

  const handleSubmit = async (values: TriggerFormValues) => {
    await onSave(values);
  };

  const handleFormError = () => {
    toast.error('Please fix the highlighted fields');
  };

  // Fetch resources (DocTypes) for the selected app when entering the resource step
  React.useEffect(() => {
    if (fromAppStep !== 'resource' || !selectedApp) return;

    let cancelled = false;
    setLoadingAppResources(true);
    getAppResources(selectedApp.app, 'recommended')
      .then((result) => {
        if (!cancelled) {
          setAppResources(result as AppResourceSummary[]);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingAppResources(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [fromAppStep, selectedApp]);

  const handleFromAppSelectApp = (app: CapabilityApp) => {
    setSelectedApp(app);
    setSelectedDoctype(null);
    setSelectedEventCapability(null);
    setFromAppStep('resource');
  };

  const handleFromAppSelectResource = (doctype: string) => {
    setSelectedDoctype(doctype);
    setFromAppStep('resource-detail');
  };

  const handleFromAppSelectEvent = (capability: CapabilityDescriptor) => {
    setSelectedEventCapability(capability);
    setFromAppStep('event');
  };

  // Actions aren't applicable to Doc Event trigger creation; ResourceDetail
  // always renders them alongside events, so this is a no-op guard.
  const handleFromAppSelectAction = () => {};

  const handleFromAppUseEvent = (triggerPayload: Record<string, unknown>) => {
    // Pre-populate the existing form state with the guided-flow payload and
    // hand off to the same Advanced form fields / save path used below —
    // this does not create or save the Agent Trigger itself.
    triggerForm.reset({
      trigger_name: '',
      trigger_type: 'Doc Event',
      active: true,
      interval_count: undefined,
      scheduled_interval: undefined,
      reference_doctype:
        typeof triggerPayload.reference_doctype === 'string'
          ? triggerPayload.reference_doctype
          : undefined,
      doc_event:
        typeof triggerPayload.doc_event === 'string' ? triggerPayload.doc_event : undefined,
      condition:
        typeof triggerPayload.condition === 'string' ? triggerPayload.condition : undefined,
      prompt_field:
        typeof triggerPayload.prompt_field === 'string' ? triggerPayload.prompt_field : undefined,
      file_attachments: [],
      app_name: undefined,
      event_name: undefined,
      webhook_slug: undefined,
      webhook_key: undefined,
    });
    setFromAppStep('form');
    setSelectedApp(null);
    setSelectedDoctype(null);
    setSelectedEventCapability(null);
    setAppResources([]);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogScrollContent className="sm:max-w-[600px]">
        <DialogScrollHeader>
          <DialogTitle>Configure trigger</DialogTitle>
          <DialogDescription>
            {editingTrigger ? 'Edit trigger configuration' : 'Add a new trigger to this agent'}
          </DialogDescription>
        </DialogScrollHeader>
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <Form {...triggerForm}>
          <form
            onSubmit={triggerForm.handleSubmit(handleSubmit, handleFormError)}
            className="flex min-h-0 flex-1 flex-col overflow-hidden"
          >
            <DialogScrollBody className="space-y-4 pb-4">
            {fromAppStep !== 'form' ? (
              <>
                {fromAppStep === 'app' && (
                  <div className="space-y-4">
                    <div className="flex items-center gap-2">
                      <Button
                        size="icon-sm"
                        variant="ghost"
                        type="button"
                        onClick={() => setFromAppStep('form')}
                      >
                        <ArrowLeft className="w-4 h-4" />
                      </Button>
                      <div>
                        <h3 className="font-medium text-sm">Choose an app</h3>
                        <p className="text-xs text-steel-soft">
                          Pick the app whose events should trigger this agent.
                        </p>
                      </div>
                    </div>
                    <AppPicker onSelect={handleFromAppSelectApp} />
                  </div>
                )}

                {fromAppStep === 'resource' && selectedApp && (
                  <div className="space-y-4">
                    <div className="flex items-center gap-2">
                      <Button
                        size="icon-sm"
                        variant="ghost"
                        type="button"
                        onClick={() => setFromAppStep('app')}
                      >
                        <ArrowLeft className="w-4 h-4" />
                      </Button>
                      <div>
                        <h3 className="font-medium text-sm">{selectedApp.title}</h3>
                        <p className="text-xs text-steel-soft">
                          Pick a resource (DocType) to trigger from.
                        </p>
                      </div>
                    </div>
                    {loadingAppResources ? (
                      <div className="flex items-center justify-center py-12">
                        <Loader2 className="w-5 h-5 animate-spin text-steel-soft" />
                      </div>
                    ) : appResources.length === 0 ? (
                      <div className="text-center py-12 border border-dashed rounded-none bg-paper-deep/20">
                        <p className="font-body text-steel-soft">
                          No resources available for this app.
                        </p>
                      </div>
                    ) : (
                      <div className="grid gap-3 sm:grid-cols-2">
                        {appResources.map((resource) => (
                          <ResourceCard
                            key={resource.doctype}
                            resource={resource}
                            onSelect={handleFromAppSelectResource}
                          />
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {fromAppStep === 'resource-detail' && selectedApp && selectedDoctype && (
                  <ResourceDetail
                    app={selectedApp.app}
                    doctype={selectedDoctype}
                    onSelectAction={handleFromAppSelectAction}
                    onSelectEvent={handleFromAppSelectEvent}
                    onBack={() => setFromAppStep('resource')}
                  />
                )}

                {fromAppStep === 'event' && selectedApp && selectedEventCapability && (
                  <EventDetail
                    app={selectedApp.app}
                    capability={selectedEventCapability}
                    onUseEvent={handleFromAppUseEvent}
                    onBack={() => setFromAppStep('resource-detail')}
                  />
                )}
              </>
            ) : (
              <>
            {/* Trigger Name Field - Only editable when adding */}
            {!editingTrigger && (
              <FormField
                control={triggerForm.control}
                name="trigger_name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Trigger name</FormLabel>
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
                <FormLabel>Trigger name</FormLabel>
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
                  <FormLabel>Trigger type</FormLabel>
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

            {/* Guided entry point: hand off Doc Event trigger creation to the
                AppPicker -> ResourceDetail -> EventDetail wizard (plan §14.3).
                Advanced path above (raw DocType + doc_event picker) is untouched. */}
            {!editingTrigger && (
              <div className="flex justify-end">
                <Button
                  type="button"
                  variant="link"
                  size="sm"
                  className="h-auto p-0 text-xs"
                  onClick={() => setFromAppStep('app')}
                >
                  Or configure from an app&apos;s events &rarr;
                </Button>
              </div>
            )}

            <FormField
              control={triggerForm.control}
              name="active"
              render={({ field }) => (
                <FormItem className="flex flex-row items-center justify-between rounded-md border p-4">
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

            {/* Doc Event extras: prompt field + file attachment mappings */}
            {watchTriggerType === 'Doc Event' && (
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              <TriggerDocEventExtras control={triggerForm.control as unknown as Control<any>} />
            )}

            {/* Schedule extras: Instant vs Batch execution mode */}
            {watchTriggerType === 'Schedule' && (
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              <TriggerScheduleExtras control={triggerForm.control as unknown as Control<any>} />
            )}
              </>
            )}

            </DialogScrollBody>

            <DialogScrollFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              {fromAppStep === 'form' && (
                <Button type="submit">
                  {editingTrigger ? 'Update' : 'Add'} Trigger
                </Button>
              )}
            </DialogScrollFooter>
          </form>
        </Form>
        </div>
      </DialogScrollContent>
    </Dialog>
  );
}

