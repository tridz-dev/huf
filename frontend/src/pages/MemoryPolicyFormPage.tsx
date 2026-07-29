import { useEffect, useState, useCallback, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { toast } from 'sonner';
import { ArrowLeft, Save, Trash2 } from 'lucide-react';
import { Form } from '@/components/ui/form';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { InlineEditName } from '@/components/common/InlineEditName';
import { db } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import {
  getMemoryPolicy,
  createMemoryPolicy,
  updateMemoryPolicy,
  deleteMemoryPolicy,
} from '@/services/memoryPolicyApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import type { MemoryPolicyDoc } from '@/types/memory';
import { memoryPolicyFormSchema, type MemoryPolicyFormValues } from '@/components/memory/memoryPolicyFormSchema';
import { PolicyTab } from '@/components/memory/tabs/PolicyTab';
import { CaptureTab } from '@/components/memory/tabs/CaptureTab';
import { RetrievalTab } from '@/components/memory/tabs/RetrievalTab';
import { GuardrailsTab } from '@/components/memory/tabs/GuardrailsTab';
import { DeleteMemoryPolicyDialog } from '@/components/memory/DeleteMemoryPolicyDialog';
import { createFormSubmitHandler, type TabFieldMapping } from '@/utils/formValidation';
import type { ComboboxOption } from '@/components/ui/combobox';

export { MemoryPolicyFormPage };
export default MemoryPolicyFormPage;

function mapDocToFormValues(doc: Partial<MemoryPolicyDoc>): MemoryPolicyFormValues {
  return {
    policy_name: doc.policy_name || '',
    enabled: doc.enabled === undefined ? true : doc.enabled === 1,
    agent: doc.agent || undefined,
    scope_type: doc.scope_type || 'Agent',
    scope_key: doc.scope_key || '',
    capture_mode: doc.capture_mode || 'Manual',
    learning_agent: doc.learning_agent || undefined,
    approval_required: doc.approval_required === undefined ? true : doc.approval_required === 1,
    default_status: doc.default_status || 'Draft',
    allowed_record_types: doc.allowed_record_types || '',
    inject_mode: doc.inject_mode || 'Tool Only',
    max_records: doc.max_records ?? 5,
    token_budget: doc.token_budget ?? 1000,
    allow_agent_write: doc.allow_agent_write === 1,
    allow_user_scope_write: doc.allow_user_scope_write === undefined ? true : doc.allow_user_scope_write === 1,
    allow_role_scope_write: doc.allow_role_scope_write === 1,
    allow_agent_scope_write: doc.allow_agent_scope_write === undefined ? true : doc.allow_agent_scope_write === 1,
    allow_site_scope_write: doc.allow_site_scope_write === 1,
    auto_promote_to_knowledge: doc.auto_promote_to_knowledge === 1,
    knowledge_source: doc.knowledge_source || undefined,
    promotion_min_confidence: doc.promotion_min_confidence ?? 0.8,
    promotion_min_importance: doc.promotion_min_importance ?? 0.6,
    ttl_days: doc.ttl_days ?? 0,
    metadata_json: doc.metadata_json || '',
  };
}

const tabConfig = {
  policy: { label: 'Policy', fields: ['policy_name', 'enabled', 'agent', 'scope_type', 'scope_key'], default: true },
  capture: {
    label: 'Capture',
    fields: ['capture_mode', 'learning_agent', 'approval_required', 'default_status', 'allowed_record_types'],
    default: false,
  },
  retrieval: { label: 'Retrieval', fields: ['inject_mode', 'max_records', 'token_budget'], default: false },
  guardrails: {
    label: 'Guardrails',
    fields: [
      'allow_agent_write',
      'allow_user_scope_write',
      'allow_role_scope_write',
      'allow_agent_scope_write',
      'allow_site_scope_write',
      'auto_promote_to_knowledge',
      'knowledge_source',
      'promotion_min_confidence',
      'promotion_min_importance',
      'ttl_days',
      'metadata_json',
    ],
    default: false,
  },
} as const;

const validTabs = Object.keys(tabConfig);
const defaultTab = Object.entries(tabConfig).find(([, c]) => c.default)?.[0] || validTabs[0];
const tabFieldMapping: TabFieldMapping = Object.fromEntries(
  Object.entries(tabConfig).map(([key, c]) => [key, [...c.fields]]),
);
const tabLabels: Record<string, string> = Object.fromEntries(
  Object.entries(tabConfig).map(([key, c]) => [key, c.label]),
);

function MemoryPolicyFormPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const isNew = id === 'new';

  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [agents, setAgents] = useState<Array<{ name: string; agent_name?: string }>>([]);
  const [knowledgeSources, setKnowledgeSources] = useState<Array<{ name: string; source_name?: string }>>([]);

  const [activeTab, setActiveTab] = useState<string>(() => {
    const hashFromUrl = window.location.hash.slice(1);
    return hashFromUrl && validTabs.includes(hashFromUrl) ? hashFromUrl : defaultTab;
  });

  useEffect(() => {
    const handleHashChange = () => {
      const hashFromUrl = window.location.hash.slice(1);
      setActiveTab(hashFromUrl && validTabs.includes(hashFromUrl) ? hashFromUrl : defaultTab);
    };
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  const handleTabChange = (value: string) => {
    setActiveTab(value);
    if (value === defaultTab) {
      window.history.replaceState(null, '', window.location.pathname);
    } else {
      window.location.hash = value;
    }
  };

  const agentOptions: ComboboxOption[] = useMemo(
    () => agents.map((a) => ({ value: a.name, label: a.agent_name || a.name })),
    [agents],
  );
  const knowledgeSourceOptions: ComboboxOption[] = useMemo(
    () => knowledgeSources.map((k) => ({ value: k.name, label: k.source_name || k.name })),
    [knowledgeSources],
  );

  const form = useForm<MemoryPolicyFormValues>({
    resolver: zodResolver(memoryPolicyFormSchema),
    defaultValues: mapDocToFormValues({}),
  });

  const loadPolicy = useCallback(
    async (name: string) => {
      try {
        const data = await getMemoryPolicy(name);
        form.reset(mapDocToFormValues(data));
      } catch (error) {
        toast.error(getFrappeErrorMessage(error) || 'Failed to load memory policy');
      }
    },
    [form],
  );

  useEffect(() => {
    if (id && !isNew) {
      loadPolicy(id).then(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, [id, isNew, loadPolicy]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [agentRows, sourceRows] = await Promise.all([
          db.getDocList(doctype.Agent, { fields: ['name', 'agent_name'], limit: 1000 }),
          db.getDocList(doctype['Knowledge Source'], { fields: ['name', 'source_name'], limit: 1000 }),
        ]);
        if (!cancelled) {
          setAgents(agentRows as Array<{ name: string; agent_name?: string }>);
          setKnowledgeSources(sourceRows as Array<{ name: string; source_name?: string }>);
        }
      } catch (error) {
        console.error('Error loading agent/knowledge source options:', error);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const onSubmit = async (values: MemoryPolicyFormValues) => {
    setSaving(true);
    try {
      const payload: Partial<MemoryPolicyDoc> = {
        policy_name: values.policy_name,
        enabled: values.enabled ? 1 : 0,
        agent: values.agent || null,
        scope_type: values.scope_type,
        scope_key: values.scope_key || null,
        capture_mode: values.capture_mode,
        learning_agent: values.learning_agent || null,
        approval_required: values.approval_required ? 1 : 0,
        default_status: values.default_status,
        allowed_record_types: values.allowed_record_types || null,
        inject_mode: values.inject_mode,
        max_records: values.max_records,
        token_budget: values.token_budget,
        allow_agent_write: values.allow_agent_write ? 1 : 0,
        allow_user_scope_write: values.allow_user_scope_write ? 1 : 0,
        allow_role_scope_write: values.allow_role_scope_write ? 1 : 0,
        allow_agent_scope_write: values.allow_agent_scope_write ? 1 : 0,
        allow_site_scope_write: values.allow_site_scope_write ? 1 : 0,
        auto_promote_to_knowledge: values.auto_promote_to_knowledge ? 1 : 0,
        knowledge_source: values.auto_promote_to_knowledge ? values.knowledge_source || null : null,
        promotion_min_confidence: values.promotion_min_confidence,
        promotion_min_importance: values.promotion_min_importance,
        ttl_days: values.ttl_days,
        metadata_json: values.metadata_json || null,
      };

      if (isNew) {
        const created = await createMemoryPolicy(payload);
        toast.success('Memory policy created');
        navigate(`/memory/policies/${encodeURIComponent(created.name)}`, { replace: true });
      } else if (id) {
        const updated = await updateMemoryPolicy(id, payload);
        toast.success('Memory policy updated');
        form.reset(mapDocToFormValues(updated));
        if (updated.name !== id) {
          navigate(`/memory/policies/${encodeURIComponent(updated.name)}`, { replace: true });
        }
      }
    } catch (error) {
      toast.error(getFrappeErrorMessage(error) || 'Failed to save memory policy');
    } finally {
      setSaving(false);
    }
  };

  const handleFormSubmit = useMemo(
    () => createFormSubmitHandler(form, activeTab, tabFieldMapping, tabLabels, onSubmit),
    [form, activeTab],
  );

  const handleDeleteConfirm = async () => {
    if (!id || isNew) return;
    setDeleting(true);
    try {
      await deleteMemoryPolicy(id);
      toast.success('Memory policy deleted');
      navigate('/memory#policies');
    } catch (error) {
      toast.error(getFrappeErrorMessage(error) || 'Failed to delete memory policy');
    } finally {
      setDeleting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="font-body text-steel-soft">Loading memory policy...</div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto">
      <div className="p-6 space-y-6 max-w-4xl mx-auto">
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div className="flex-1 space-y-2">
            <Button
              variant="ghost"
              size="sm"
              className="-ml-2 text-steel-soft"
              onClick={() => navigate('/memory#policies')}
            >
              <ArrowLeft className="w-4 h-4 mr-2" />
              Back to Policies
            </Button>
            <div className="flex items-center gap-3 flex-wrap">
              {isNew ? (
                <Input
                  value={form.watch('policy_name')}
                  onChange={(e) => form.setValue('policy_name', e.target.value, { shouldDirty: true })}
                  className="text-2xl font-bold h-auto border-0 px-0 focus-visible:ring-0 max-w-md"
                  placeholder="Policy Name"
                />
              ) : (
                <InlineEditName
                  value={form.watch('policy_name')}
                  onChange={(value) => form.setValue('policy_name', value, { shouldDirty: true })}
                  placeholder="Policy Name"
                />
              )}
              <Badge variant={form.watch('enabled') ? 'default' : 'secondary'}>
                {form.watch('enabled') ? 'Enabled' : 'Disabled'}
              </Badge>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {!isNew && (
              <Button
                variant="outline"
                size="sm"
                className="text-destructive hover:text-destructive"
                onClick={() => setDeleteOpen(true)}
              >
                <Trash2 className="w-4 h-4 mr-2" />
                Delete
              </Button>
            )}
            <Button size="sm" onClick={handleFormSubmit} disabled={saving}>
              <Save className="w-4 h-4 mr-2" />
              {saving ? 'Saving...' : 'Save'}
            </Button>
          </div>
        </div>

        <Form {...form}>
          <form onSubmit={handleFormSubmit} className="space-y-6">
            <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">
              <TabsList layout="grid" cols={4}>
                {Object.entries(tabConfig).map(([tabKey, config]) => (
                  <TabsTrigger key={tabKey} value={tabKey}>
                    {config.label}
                  </TabsTrigger>
                ))}
              </TabsList>

              <TabsContent value="policy" className="space-y-4">
                <PolicyTab form={form} isNew={isNew} agentOptions={agentOptions} />
              </TabsContent>

              <TabsContent value="capture" className="space-y-4">
                <CaptureTab form={form} agentOptions={agentOptions} />
              </TabsContent>

              <TabsContent value="retrieval" className="space-y-4">
                <RetrievalTab form={form} />
              </TabsContent>

              <TabsContent value="guardrails" className="space-y-4">
                <GuardrailsTab form={form} knowledgeSourceOptions={knowledgeSourceOptions} />
              </TabsContent>
            </Tabs>
          </form>
        </Form>

        {!isNew && id && (
          <DeleteMemoryPolicyDialog
            open={deleteOpen}
            onOpenChange={setDeleteOpen}
            policyName={form.watch('policy_name') || id}
            onConfirm={handleDeleteConfirm}
            loading={deleting}
          />
        )}
      </div>
    </div>
  );
}
