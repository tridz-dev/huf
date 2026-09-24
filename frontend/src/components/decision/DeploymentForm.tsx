import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
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
import { Loader2 } from 'lucide-react';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';
import { call } from '@/lib/frappe-sdk';

interface DeploymentFormProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: () => void;
  decisionModel?: string;
}

interface DeploymentFormData {
  decision_model: string;
  ai_model: string;
  wire_protocol: string;
  endpoint_path: string;
}

const defaultFormData: DeploymentFormData = {
  decision_model: '',
  ai_model: '',
  wire_protocol: 'systemone',
  endpoint_path: '',
};

export function DeploymentForm({
  isOpen,
  onClose,
  onSuccess,
  decisionModel,
}: DeploymentFormProps) {
  const [saving, setSaving] = useState(false);
  const [models, setModels] = useState<Record<string, any>[]>([]);
  const [loadingModels, setLoadingModels] = useState(false);
  const form = useForm<DeploymentFormData>({
    defaultValues: {
      ...defaultFormData,
      decision_model: decisionModel || '',
    },
  });

  useEffect(() => {
    if (isOpen) {
      loadModels();
    }
  }, [isOpen]);

  const loadModels = async () => {
    setLoadingModels(true);
    try {
      // Fetch AI Models with Decision modality
      const response = await call.get('frappe.client.get_list', {
        doctype: 'AI Model',
        filters: [['modalities', 'like', '%Decision%']],
        fields: ['name', 'model_name', 'provider', 'modalities'],
      });
      setModels(response.message || []);
    } catch (error) {
      toast.error('Failed to load AI models');
    } finally {
      setLoadingModels(false);
    }
  };

  const onSubmit = async (data: DeploymentFormData) => {
    setSaving(true);
    try {
      await call.post('frappe.client.insert', {
        doctype: 'Decision Deployment',
        decision_model: data.decision_model,
        ai_model: data.ai_model,
        wire_protocol: data.wire_protocol,
        endpoint_path: data.endpoint_path || undefined,
      });
      toast.success('Deployment created successfully');
      form.reset(defaultFormData);
      onClose();
      onSuccess?.();
    } catch (error: any) {
      toast.error(error?.message || 'Failed to create deployment');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Create Deployment</DialogTitle>
          <DialogDescription>
            Add a new deployment for a decision model
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="decision_model"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Decision Model</FormLabel>
                  <FormControl>
                    <Input
                      {...field}
                      placeholder="e.g., Jev 1.13"
                      disabled={Boolean(decisionModel)}
                    />
                  </FormControl>
                  <FormDescription>
                    The decision model this deployment provides
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="ai_model"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>AI Model</FormLabel>
                  <Select value={field.value} onValueChange={field.onChange}>
                    <FormControl>
                      <SelectTrigger disabled={loadingModels}>
                        <SelectValue placeholder="Select an AI model" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {models.map((model) => (
                        <SelectItem key={model.name} value={model.name}>
                          {model.model_name} ({model.provider})
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormDescription>
                    Decision-modality AI model to host this deployment
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="wire_protocol"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Wire Protocol</FormLabel>
                  <Select value={field.value} onValueChange={field.onChange}>
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="Select protocol" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      <SelectItem value="systemone">System One</SelectItem>
                      <SelectItem value="openrouter">OpenRouter</SelectItem>
                      <SelectItem value="local">Local</SelectItem>
                    </SelectContent>
                  </Select>
                  <FormDescription>
                    Communication protocol for this deployment
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="endpoint_path"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Endpoint Path (optional)</FormLabel>
                  <FormControl>
                    <Input
                      {...field}
                      placeholder="/v1/judge"
                      type="text"
                    />
                  </FormControl>
                  <FormDescription>
                    Custom API endpoint path if needed
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={onClose}
                disabled={saving}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={saving}>
                {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Create Deployment
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
