import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Save, Trash2 } from 'lucide-react';
import { UseFormReturn } from 'react-hook-form';
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { deleteKnowledgeSource } from '@/services/knowledgeApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import type { AIProvider } from '@/types/agent.types';
import type { KnowledgeSourceDoc } from '@/types/knowledge.types';
import { BasicsFields } from './BasicsFields';
import { GeneralTab } from './GeneralTab';
import { ConfirmActionDialog } from './import/ConfirmActionDialog';
import type { KnowledgeSourceFormValues } from './types';

interface SettingsTabProps {
  form: UseFormReturn<KnowledgeSourceFormValues>;
  source: KnowledgeSourceDoc;
  providers: AIProvider[];
  documentCount: number;
  dirty: boolean;
  saving: boolean;
  onSave: () => void;
}

export function SettingsTab({ form, source, providers, documentCount, dirty, saving, onSave }: SettingsTabProps) {
  const navigate = useNavigate();
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const confirmDelete = async () => {
    setDeleting(true);
    try {
      await deleteKnowledgeSource(source.name);
      toast.success('Knowledge source deleted');
      navigate('/knowledge', { replace: true });
    } catch (error) {
      toast.error(getFrappeErrorMessage(error) || 'Could not delete this knowledge source');
      setDeleting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-steel" data-testid="settings-stats">
          {documentCount.toLocaleString()} {documentCount === 1 ? 'document' : 'documents'} ·{' '}
          {(source.total_chunks ?? 0).toLocaleString()} parts prepared for search
        </p>
        <Button type="button" size="sm" onClick={onSave} disabled={!dirty || saving} data-testid="save-settings">
          <Save className="mr-2 h-4 w-4" />
          {saving ? 'Saving...' : 'Save'}
        </Button>
      </div>

      <BasicsFields form={form} showDisabled />

      <Accordion type="single" collapsible className="rounded-md border px-4">
        <AccordionItem value="advanced" className="border-b-0">
          <AccordionTrigger>Advanced</AccordionTrigger>
          <AccordionContent>
            <GeneralTab form={form} providers={providers} />
          </AccordionContent>
        </AccordionItem>
      </Accordion>

      <Card className="border-destructive/40">
        <CardHeader>
          <CardTitle className="text-destructive">Danger zone</CardTitle>
          <CardDescription>Deleting removes this source and all of its documents.</CardDescription>
        </CardHeader>
        <CardContent>
          <Button type="button" variant="outline" className="text-destructive" onClick={() => setDeleteOpen(true)} data-testid="delete-source">
            <Trash2 className="mr-2 h-4 w-4" />
            Delete source
          </Button>
        </CardContent>
      </Card>

      <ConfirmActionDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title="Delete this knowledge source?"
        description="This removes the source and all of its documents. Agents using it will lose access. This cannot be undone."
        confirmLabel="Delete source"
        destructive
        busy={deleting}
        onConfirm={confirmDelete}
      />
    </div>
  );
}
