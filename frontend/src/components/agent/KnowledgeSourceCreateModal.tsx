import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Dialog, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import {
  DialogScrollBody,
  DialogScrollContent,
  DialogScrollFooter,
  DialogScrollHeader,
} from '@/components/ui/dialog-scroll';
import {
  KnowledgeSourceForm,
  mapDocToFormValues,
  buildKnowledgeSourcePayload,
} from '@/components/knowledge/KnowledgeSourceForm';
import { knowledgeSourceFormSchema, type KnowledgeSourceFormValues } from '@/components/knowledge/types';
import { createKnowledgeSource } from '@/services/knowledgeApi';
import { getProviders } from '@/services/providerApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import type { AIProvider } from '@/types/agent.types';
import type { KnowledgeSourceDoc } from '@/types/knowledge.types';

interface KnowledgeSourceCreateModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (source: KnowledgeSourceDoc) => void;
}

/**
 * In-context "create a knowledge source" dialog, used from the agent editor
 * so users don't lose their in-progress agent form (see AgentKnowledgeModal).
 * Renders the same field logic as the standalone /knowledge/new route via
 * the shared KnowledgeSourceForm, but only creates the doc locally and hands
 * the result back via onCreated — no navigation, no agent linking (the
 * agent-linking side effect is handled by the caller).
 */
export function KnowledgeSourceCreateModal({
  open,
  onOpenChange,
  onCreated,
}: KnowledgeSourceCreateModalProps) {
  const [saving, setSaving] = useState(false);
  const [providers, setProviders] = useState<AIProvider[]>([]);

  const form = useForm<KnowledgeSourceFormValues>({
    resolver: zodResolver(knowledgeSourceFormSchema),
    defaultValues: mapDocToFormValues({}),
  });

  useEffect(() => {
    if (!open) return;
    form.reset(mapDocToFormValues({}));
    getProviders()
      .then((data) => setProviders(data as AIProvider[]))
      .catch((err) => console.error('Error loading providers:', err));
  }, [open, form]);

  const handleOpenChange = (next: boolean) => {
    if (!next && form.formState.isDirty) {
      const confirmed = window.confirm('Discard this knowledge source? Your changes will be lost.');
      if (!confirmed) return;
    }
    onOpenChange(next);
  };

  const onSubmit = async (values: KnowledgeSourceFormValues) => {
    setSaving(true);
    try {
      const payload = buildKnowledgeSourcePayload(values);
      const created = await createKnowledgeSource(payload);
      toast.success('Knowledge source created');
      onCreated(created);
      onOpenChange(false);
    } catch (error) {
      console.error('Error creating knowledge source:', error);
      const msg = getFrappeErrorMessage(error);
      toast.error(msg || 'Failed to create knowledge source');
    } finally {
      setSaving(false);
    }
  };

  const handleFormSubmit = form.handleSubmit(onSubmit, () => {
    toast.error('Please fix the highlighted fields');
  });

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogScrollContent className="sm:max-w-2xl">
        <DialogScrollHeader>
          <DialogTitle>New Knowledge Source</DialogTitle>
          <DialogDescription>
            Register a knowledge source your agents can retrieve context from.
          </DialogDescription>
        </DialogScrollHeader>

        <KnowledgeSourceForm
          form={form}
          isNew
          providers={providers}
          showStatusTab={false}
          onSubmit={handleFormSubmit}
          className="flex min-h-0 flex-1 flex-col overflow-hidden"
          bodyWrapper={(children) => (
            <DialogScrollBody className="space-y-4 pb-4">{children}</DialogScrollBody>
          )}
          footer={
            <DialogScrollFooter>
              <Button type="button" variant="outline" onClick={() => handleOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={saving}>
                {saving ? 'Creating...' : 'Create'}
              </Button>
            </DialogScrollFooter>
          }
        />
      </DialogScrollContent>
    </Dialog>
  );
}
