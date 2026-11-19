import { useEffect, useState } from 'react';
import { UseFormReturn } from 'react-hook-form';
import { Form } from '@/components/ui/form';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import type { AIProvider } from '@/types/agent.types';
import type { KnowledgeInputDoc, KnowledgeSourceDoc } from '@/types/knowledge.types';
import { DocumentsTab } from './DocumentsTab';
import { KnowledgeActivityTab } from './KnowledgeActivityTab';
import { KnowledgeSourceHeader } from './KnowledgeSourceHeader';
import { KnowledgeTestTab } from './KnowledgeTestTab';
import { SettingsTab } from './SettingsTab';
import { useKnowledgeOverview } from './useKnowledgeOverview';
import type { KnowledgeSourceFormValues } from './types';

const TABS = ['documents', 'test', 'activity', 'settings'] as const;
type TabKey = (typeof TABS)[number];

function tabFromHash(): TabKey {
  const hash = window.location.hash.slice(1) as TabKey;
  return TABS.includes(hash) ? hash : 'documents';
}

interface KnowledgeSourceViewProps {
  form: UseFormReturn<KnowledgeSourceFormValues>;
  source: KnowledgeSourceDoc;
  providers: AIProvider[];
  inputs: KnowledgeInputDoc[];
  inputsLoading: boolean;
  dirty: boolean;
  saving: boolean;
  rebuilding: boolean;
  fromAgent?: string;
  addOpen: boolean;
  onAddOpenChange: (open: boolean) => void;
  onSubmit: () => void;
  onCancel?: () => void;
  onRebuildIndex: () => void;
  onToggleDisabled: () => void;
  /** Refetch source + inputs (never saves the source). */
  onChanged: () => void;
  onReprocessInput: (name: string) => Promise<void> | void;
  onDeleteInput: (name: string) => Promise<void> | void;
}

/** Existing-source page: header plus Documents | Test | Activity | Settings tabs. */
export function KnowledgeSourceView(props: KnowledgeSourceViewProps) {
  const { form, source, inputs } = props;
  const [tab, setTab] = useState<TabKey>(tabFromHash);
  const overview = useKnowledgeOverview(source.name, source, inputs);

  useEffect(() => {
    const onHash = () => setTab(tabFromHash());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  const changeTab = (value: string) => {
    setTab(value as TabKey);
    if (value === 'documents') window.history.replaceState(null, '', window.location.pathname);
    else window.location.hash = value;
  };

  return (
    <>
      <KnowledgeSourceHeader
        form={form}
        isNew={false}
        health={overview.health}
        disabled={source.disabled === 1}
        saving={props.saving}
        rebuilding={props.rebuilding}
        sourceStatus={source.status}
        fromAgent={props.fromAgent}
        onSave={props.onSubmit}
        onCancel={props.onCancel}
        onRebuildIndex={props.onRebuildIndex}
        onAddContent={() => props.onAddOpenChange(true)}
        onTest={() => changeTab('test')}
        onToggleDisabled={props.onToggleDisabled}
      />
      <Form {...form}>
        <form onSubmit={props.onSubmit} className="space-y-6">
          <Tabs value={tab} onValueChange={changeTab} className="w-full">
            <TabsList layout="grid" cols={4}>
              <TabsTrigger value="documents">Documents</TabsTrigger>
              <TabsTrigger value="test">Test</TabsTrigger>
              <TabsTrigger value="activity">Activity</TabsTrigger>
              <TabsTrigger value="settings">Settings</TabsTrigger>
            </TabsList>
            <TabsContent value="documents" className="space-y-4">
              <DocumentsTab
                knowledgeSource={source.name}
                source={source}
                inputs={inputs}
                inputsLoading={props.inputsLoading}
                counts={overview.counts}
                active={overview.active}
                latest={overview.latest}
                addOpen={props.addOpen}
                onAddOpenChange={props.onAddOpenChange}
                onRefreshOverview={overview.refresh}
                onChanged={props.onChanged}
                onReprocess={props.onReprocessInput}
                onRemove={props.onDeleteInput}
              />
            </TabsContent>
            <TabsContent value="test">
              <KnowledgeTestTab source={source} />
            </TabsContent>
            <TabsContent value="activity">
              <KnowledgeActivityTab knowledgeSource={source.name} refreshKey={overview.bump} />
            </TabsContent>
            <TabsContent value="settings">
              <SettingsTab
                form={form}
                source={source}
                providers={props.providers}
                documentCount={overview.counts.total}
                dirty={props.dirty}
                saving={props.saving}
                onSave={props.onSubmit}
              />
            </TabsContent>
          </Tabs>
        </form>
      </Form>
    </>
  );
}
