import { useEffect, useState, useMemo, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Form } from '../components/ui/form';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { toast } from 'sonner';
import {
  getKnowledgeSource,
  createKnowledgeSource,
  updateKnowledgeSource,
  rebuildIndex,
} from '../services/knowledgeApi';
import { getFrappeErrorMessage } from '../lib/frappe-error';
import { KnowledgeSourceHeader } from '../components/knowledge/KnowledgeSourceHeader';
import { GeneralTab } from '../components/knowledge/GeneralTab';
import { StatusTab } from '../components/knowledge/StatusTab';
import { KnowledgeInputsModal } from '../components/knowledge/KnowledgeInputsModal';
import {
  knowledgeSourceFormSchema,
  type KnowledgeSourceFormValues,
} from '../components/knowledge/types';
import type { KnowledgeSourceDoc } from '../types/knowledge.types';
import { createFormSubmitHandler, type TabFieldMapping } from '../utils/formValidation';

export { KnowledgeSourceFormPage };
export default KnowledgeSourceFormPage;

function mapDocToFormValues(doc: Partial<KnowledgeSourceDoc>): KnowledgeSourceFormValues {
  return {
    source_name: doc.source_name || '',
    description: doc.description || '',
    knowledge_type: doc.knowledge_type || 'sqlite_fts',
    scope: doc.scope || 'Site',
    storage_mode: doc.storage_mode || 'Frappe File',
    chunk_size: doc.chunk_size ?? 512,
    chunk_overlap: doc.chunk_overlap ?? 50,
    disabled: doc.disabled === 1,
    embedding_model: doc.embedding_model || '',
    vector_dimension: doc.vector_dimension ?? 1536,
    embedding_provider: doc.embedding_provider || '',
  };
}

function KnowledgeSourceFormPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const isNew = id === 'new';

  const tabConfig = {
    general: {
      label: 'General',
      fields: [
        'source_name',
        'description',
        'knowledge_type',
        'scope',
        'storage_mode',
        'chunk_size',
        'chunk_overlap',
        'embedding_model',
        'vector_dimension',
        'embedding_provider',
      ],
      default: true,
      disabled: false,
    },
    status: {
      label: 'Status',
      fields: [],
      default: false,
      disabled: isNew,
    },
  } as const;

  const validTabs = useMemo(() => Object.keys(tabConfig), []);
  const defaultTab = useMemo(
    () => Object.entries(tabConfig).find(([, config]) => config.default)?.[0] || validTabs[0],
    [validTabs],
  );
  const tabFieldMapping: TabFieldMapping = useMemo(
    () =>
      Object.fromEntries(
        Object.entries(tabConfig).map(([key, config]) => [key, [...config.fields]]),
      ),
    [],
  );
  const tabLabels = useMemo(
    () =>
      Object.fromEntries(
        Object.entries(tabConfig).map(([key, config]) => [key, config.label]),
      ),
    [],
  );

  const [activeTab, setActiveTab] = useState<string>(() => {
    const hashFromUrl = window.location.hash.slice(1);
    return hashFromUrl && validTabs.includes(hashFromUrl) ? hashFromUrl : defaultTab;
  });

  useEffect(() => {
    const handleHashChange = () => {
      const hashFromUrl = window.location.hash.slice(1);
      const tab = hashFromUrl && validTabs.includes(hashFromUrl) ? hashFromUrl : defaultTab;
      setActiveTab(tab);
    };
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, [defaultTab, validTabs]);

  const handleTabChange = (value: string) => {
    setActiveTab(value);
    if (value === defaultTab) {
      window.history.replaceState(null, '', window.location.pathname);
    } else {
      window.location.hash = value;
    }
  };

  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);
  const [rebuilding, setRebuilding] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [inputsModalOpen, setInputsModalOpen] = useState(false);
  const [sourceDoc, setSourceDoc] = useState<KnowledgeSourceDoc | null>(null);

  const form = useForm<KnowledgeSourceFormValues>({
    resolver: zodResolver(knowledgeSourceFormSchema),
    defaultValues: mapDocToFormValues({}),
  });

  const watchDisabled = form.watch('disabled');
  const isDirty = form.formState.isDirty;
  const [initialDisabled, setInitialDisabled] = useState(false);
  const disabledChanged = watchDisabled !== initialDisabled;
  const showSaveButton = isNew || isDirty || disabledChanged;

  const loadSource = useCallback(
    async (name: string) => {
      try {
        const data = await getKnowledgeSource(name);
        setSourceDoc(data);
        const formValues = mapDocToFormValues(data);
        form.reset(formValues);
        setInitialDisabled(formValues.disabled);
      } catch (error) {
        console.error('Error loading knowledge source:', error);
        const msg = getFrappeErrorMessage(error);
        toast.error(msg || 'Failed to load knowledge source');
      }
    },
    [form],
  );

  useEffect(() => {
    if (id && !isNew) {
      loadSource(id).then(() => setLoading(false));
    } else if (isNew) {
      setLoading(false);
    }
  }, [id, isNew, loadSource]);

  const onSubmit = async (values: KnowledgeSourceFormValues) => {
    setSaving(true);
    try {
      const payload: Partial<KnowledgeSourceDoc> = {
        source_name: values.source_name,
        description: values.description || '',
        knowledge_type: values.knowledge_type,
        scope: values.scope,
        storage_mode: values.storage_mode as KnowledgeSourceDoc['storage_mode'],
        chunk_size: values.chunk_size,
        chunk_overlap: values.chunk_overlap,
        disabled: values.disabled ? 1 : 0,
        embedding_model: values.embedding_model || '',
        vector_dimension: values.vector_dimension ?? 1536,
        embedding_provider: values.embedding_provider || '',
      };

      if (isNew) {
        const created = await createKnowledgeSource(payload);
        toast.success('Knowledge source created');
        setSourceDoc(created);
        const formValues = mapDocToFormValues(created);
        form.reset(formValues);
        setInitialDisabled(formValues.disabled);
        navigate(`/knowledge/${created.name}`);
      } else if (id) {
        const updated = await updateKnowledgeSource(id, payload);
        toast.success('Knowledge source updated');
        setSourceDoc(updated);
        const formValues = mapDocToFormValues(updated);
        form.reset(formValues);
        setInitialDisabled(formValues.disabled);
      }
    } catch (error) {
      console.error('Error saving knowledge source:', error);
      const msg = getFrappeErrorMessage(error);
      toast.error(msg || 'Failed to save knowledge source');
    } finally {
      setSaving(false);
    }
  };

  const handleFormSubmit = useMemo(
    () => createFormSubmitHandler(form, activeTab, tabFieldMapping, tabLabels, onSubmit),
    [form, activeTab, tabFieldMapping, tabLabels],
  );

  const handleRebuildIndex = async () => {
    if (!id || isNew) return;
    setRebuilding(true);
    try {
      await rebuildIndex(id);
      toast.success('Rebuild started. Refresh to check progress.');
      await loadSource(id);
    } catch (error) {
      const msg = getFrappeErrorMessage(error);
      toast.error(msg || 'Failed to start rebuild');
    } finally {
      setRebuilding(false);
    }
  };

  const handleRefresh = async () => {
    if (!id || isNew) return;
    setRefreshing(true);
    try {
      await loadSource(id);
      toast.success('Refreshed');
    } catch {
      toast.error('Failed to refresh');
    } finally {
      setRefreshing(false);
    }
  };

  const handleSourceChanged = async () => {
    if (id && !isNew) {
      await loadSource(id);
    }
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-muted-foreground">Loading knowledge source...</div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto">
      <div className="p-6 space-y-6 max-w-6xl mx-auto">
        <KnowledgeSourceHeader
          form={form}
          watchDisabled={watchDisabled}
          isNew={isNew}
          showSaveButton={showSaveButton}
          saving={saving}
          rebuilding={rebuilding}
          refreshing={refreshing}
          sourceStatus={sourceDoc?.status}
          onSave={handleFormSubmit}
          onRebuildIndex={handleRebuildIndex}
          onRefresh={handleRefresh}
          onOpenInputs={() => setInputsModalOpen(true)}
        />

        <Form {...form}>
          <form onSubmit={handleFormSubmit} className="space-y-6">
            <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">
              <TabsList className="grid w-full grid-cols-2">
                {Object.entries(tabConfig).map(([tabKey, config]) => (
                  <TabsTrigger key={tabKey} value={tabKey} disabled={config.disabled}>
                    {config.label}
                  </TabsTrigger>
                ))}
              </TabsList>

              <TabsContent value="general" className="space-y-4">
                <GeneralTab form={form} isNew={isNew} />
              </TabsContent>

              <TabsContent value="status" className="space-y-4">
                <StatusTab source={sourceDoc} />
              </TabsContent>
            </Tabs>
          </form>
        </Form>

        {!isNew && id && (
          <KnowledgeInputsModal
            open={inputsModalOpen}
            onOpenChange={setInputsModalOpen}
            knowledgeSource={id}
            onSourceChanged={handleSourceChanged}
          />
        )}
      </div>
    </div>
  );
}
