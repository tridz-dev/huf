import { useEffect, useState, useMemo, useCallback, useRef } from 'react';
import { useParams, useNavigate, useBlocker, useSearchParams, type Location } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { toast } from 'sonner';
import {
  getKnowledgeSource,
  createKnowledgeSource,
  updateKnowledgeSource,
  rebuildIndex,
} from '../services/knowledgeApi';
import { getProviders } from '../services/providerApi';
import type { AIProvider } from '../types/agent.types';
import { getFrappeErrorMessage } from '../lib/frappe-error';
import { KnowledgeSourceHeader } from '../components/knowledge/KnowledgeSourceHeader';
import { KnowledgeInputsModal } from '../components/knowledge/KnowledgeInputsModal';
import { knowledgeSourceFormSchema, type KnowledgeSourceFormValues } from '../components/knowledge/types';
import {
  KnowledgeSourceForm,
  knowledgeSourceTabConfig,
  mapDocToFormValues,
  buildKnowledgeSourcePayload,
} from '../components/knowledge/KnowledgeSourceForm';
import type { KnowledgeSourceDoc } from '../types/knowledge.types';
import { createFormSubmitHandler, type TabFieldMapping } from '../utils/formValidation';
import { useSaveShortcut } from '../hooks/useSaveShortcut';
import { UnsavedChangesDialog } from '../components/UnsavedChangesDialog';
import { linkKnowledgeToAgent } from '../services/agentApi';

export { KnowledgeSourceFormPage };
export default KnowledgeSourceFormPage;

function KnowledgeSourceFormPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const fromAgent = searchParams.get('agent');
  const isNew = id === 'new';
  const skipBlockRef = useRef(false);

  const tabConfig = knowledgeSourceTabConfig;

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
  const [providers, setProviders] = useState<AIProvider[]>([]);
  const allowNavigationRef = useRef(false);

  const form = useForm<KnowledgeSourceFormValues>({
    resolver: zodResolver(knowledgeSourceFormSchema),
    defaultValues: mapDocToFormValues({}),
  });

  const watchDisabled = form.watch('disabled');
  const isDirty = form.formState.isDirty;
  const [initialDisabled, setInitialDisabled] = useState(false);
  const disabledChanged = watchDisabled !== initialDisabled;
  const showSaveButton = isNew || isDirty || disabledChanged;
  // Deliberately excludes `isNew` - a blank new-source form has nothing to
  // lose, so it shouldn't block navigation until the user actually changes something.
  const hasUnsavedChanges = isDirty || disabledChanged;

  const shouldBlock = useCallback(
    ({ currentLocation, nextLocation }: { currentLocation: Location; nextLocation: Location }) => {
      if (skipBlockRef.current) {
        skipBlockRef.current = false;
        return false;
      }
      if (allowNavigationRef.current) return false;
      if (!hasUnsavedChanges) return false;
      return (
        currentLocation.pathname !== nextLocation.pathname ||
        currentLocation.search !== nextLocation.search
      );
    },
    [hasUnsavedChanges]
  );

  const blocker = useBlocker(shouldBlock);

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
    getProviders()
      .then((data) => setProviders(data as AIProvider[]))
      .catch((err) => console.error('Error loading providers:', err));
  }, []);

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
      const payload = buildKnowledgeSourcePayload(values);

      if (isNew) {
        const created = await createKnowledgeSource(payload);
        const formValues = mapDocToFormValues(created);
        form.reset(formValues);
        setInitialDisabled(formValues.disabled);

        if (fromAgent) {
          const linkedRow = await linkKnowledgeToAgent(fromAgent, created.name);
          toast.success('Knowledge source created and linked to agent');
          allowNavigationRef.current = true;
          navigate(`/agents/${fromAgent}#knowledge`, {
            state: { linkedKnowledge: linkedRow, showTab: 'knowledge' },
            replace: true,
          });
          return;
        }

        toast.success('Knowledge source created');
        setSourceDoc(created);
        allowNavigationRef.current = true;
        navigate(`/knowledge/${created.name}`);
      } else if (id) {
        const updated = await updateKnowledgeSource(id, payload);
        toast.success('Knowledge source updated');
        setSourceDoc(updated);
        const formValues = mapDocToFormValues(updated);
        form.reset(formValues);
        setInitialDisabled(formValues.disabled);

        if (updated.name && updated.name !== id) {
          skipBlockRef.current = true;
          navigate(`/knowledge/${encodeURIComponent(updated.name)}`, { replace: true });
          return;
        }
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

  useSaveShortcut({
    onSave: handleFormSubmit,
    enabled: showSaveButton,
    isSubmitting: saving,
  });

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

  const handleCancel = () => {
    navigate(-1);
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="font-body text-steel-soft">Loading knowledge source...</div>
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
          fromAgent={fromAgent || undefined}
          onSave={handleFormSubmit}
          onCancel={fromAgent ? handleCancel : undefined}
          onRebuildIndex={handleRebuildIndex}
          onRefresh={handleRefresh}
          onOpenInputs={() => setInputsModalOpen(true)}
        />

        <KnowledgeSourceForm
          form={form}
          isNew={isNew}
          providers={providers}
          sourceDoc={sourceDoc}
          showStatusTab
          activeTab={activeTab}
          onTabChange={handleTabChange}
          onSubmit={handleFormSubmit}
        />

        {!isNew && id && (
          <KnowledgeInputsModal
            open={inputsModalOpen}
            onOpenChange={setInputsModalOpen}
            knowledgeSource={id}
            onSourceChanged={handleSourceChanged}
          />
        )}

        <UnsavedChangesDialog blocker={blocker} />
      </div>
    </div>
  );
}
