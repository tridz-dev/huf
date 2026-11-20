import type { UseFormReturn } from 'react-hook-form';
import { Save } from 'lucide-react';
import { DangerZone, SettingsAdvanced, SettingsSection, SettingsSheet } from '@/components/patterns';
import { Button } from '@/components/ui/button';
import { Form } from '@/components/ui/form';
import type { AIProvider } from '@/types/agent.types';
import type { KnowledgeSourceDoc } from '@/types/knowledge.types';
import { BasicsFields } from '../BasicsFields';
import { GeneralTab } from '../GeneralTab';
import type { KnowledgeSourceFormValues } from '../types';

interface SourceSettingsSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  form: UseFormReturn<KnowledgeSourceFormValues>;
  source: KnowledgeSourceDoc;
  providers: AIProvider[];
  documentCount: number;
  dirty: boolean;
  saving: boolean;
  onSave: () => void;
  /** Opens the confirm dialog; the sheet never deletes directly. */
  onDelete: () => void;
}

export function SourceSettingsSheet({ open, onOpenChange, form, source, providers, documentCount, dirty, saving, onSave, onDelete }: SourceSettingsSheetProps) {
  const docs = documentCount.toLocaleString();
  return (
    <SettingsSheet
      open={open}
      onOpenChange={onOpenChange}
      title="Settings"
      description={source.source_name || source.name}
      footer={
        <Button type="button" size="sm" onClick={onSave} disabled={!dirty || saving} data-testid="save-settings">
          <Save aria-hidden="true" className="mr-2 h-4 w-4" />
          {saving ? 'Saving...' : 'Save'}
        </Button>
      }
    >
      <Form {...form}>
        <SettingsSection>
          <BasicsFields form={form} showName showDisabled />
        </SettingsSection>
        <SettingsAdvanced>
          <GeneralTab form={form} providers={providers} />
        </SettingsAdvanced>
      </Form>
      <DangerZone
        title="Delete this source"
        description={`Removes all ${docs} ${documentCount === 1 ? 'document' : 'documents'}. This can't be undone.`}
        actionLabel="Delete"
        onAction={onDelete}
      />
    </SettingsSheet>
  );
}
