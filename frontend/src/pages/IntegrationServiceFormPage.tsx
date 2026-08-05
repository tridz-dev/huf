import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { toast } from 'sonner';
import { Form } from '@/components/ui/form';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { IntegrationServiceHeader } from '@/components/integration-services/IntegrationServiceHeader';
import { GeneralTab } from '@/components/integration-services/GeneralTab';
import { CredentialsSchemaTab } from '@/components/integration-services/CredentialsSchemaTab';
import {
  defaultIntegrationServiceFormValues,
  integrationServiceFormSchema,
  type IntegrationServiceFormValues,
} from '@/components/integration-services/types';
import {
  createIntegrationService,
  deleteIntegrationService,
  getIntegrationService,
  updateIntegrationService,
} from '@/services/integrationApi';
import {
  parseRequiredCredentials,
  serializeRequiredCredentials,
  type IntegrationServiceDoc,
} from '@/types/integration.types';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { createFormSubmitHandler, type TabFieldMapping } from '@/utils/formValidation';
import { useSaveShortcut } from '@/hooks/useSaveShortcut';

function mapDocToFormValues(doc: IntegrationServiceDoc): IntegrationServiceFormValues {
  return {
    service_name: doc.service_name,
    category: (doc.category as IntegrationServiceFormValues['category']) || 'Other',
    description: doc.description || '',
    documentation_url: doc.documentation_url || '',
    required_credentials: parseRequiredCredentials(doc.required_credentials).map((item) => ({
      key: item.key,
      label: item.label,
      required: item.required !== false,
      description: item.description || '',
    })),
  };
}

function mapFormToPayload(values: IntegrationServiceFormValues) {
  return {
    service_name: values.service_name.trim(),
    category: values.category,
    description: values.description?.trim() || '',
    documentation_url: values.documentation_url?.trim() || '',
    required_credentials: serializeRequiredCredentials(values.required_credentials),
  };
}

export function IntegrationServiceFormPage() {
  const { serviceId } = useParams<{ serviceId: string }>();
  const navigate = useNavigate();
  const isNew = serviceId === 'new';

  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [isBuiltin, setIsBuiltin] = useState(false);

  const tabConfig = useMemo(
    () => ({
      general: {
        label: 'General',
        fields: ['service_name', 'category', 'description', 'documentation_url'],
        default: true,
        disabled: false,
      },
      credentials: {
        label: 'Credential schema',
        fields: ['required_credentials'],
        default: false,
        disabled: false,
      },
    }),
    [],
  );

  const validTabs = useMemo(() => Object.keys(tabConfig), [tabConfig]);
  const defaultTab = useMemo(
    () => Object.entries(tabConfig).find(([, config]) => config.default)?.[0] || validTabs[0],
    [tabConfig, validTabs],
  );
  const tabFieldMapping: TabFieldMapping = useMemo(
    () =>
      Object.fromEntries(
        Object.entries(tabConfig).map(([key, config]) => [key, [...config.fields]]),
      ),
    [tabConfig],
  );
  const tabLabels = useMemo(
    () =>
      Object.fromEntries(
        Object.entries(tabConfig).map(([key, config]) => [key, config.label]),
      ),
    [tabConfig],
  );

  const [activeTab, setActiveTab] = useState<string>(() => {
    const hashFromUrl = window.location.hash.slice(1);
    return hashFromUrl && validTabs.includes(hashFromUrl) ? hashFromUrl : defaultTab;
  });

  useEffect(() => {
    if (!validTabs.includes(activeTab)) {
      setActiveTab(defaultTab);
    }
  }, [validTabs, activeTab, defaultTab]);

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

  const form = useForm<IntegrationServiceFormValues>({
    resolver: zodResolver(integrationServiceFormSchema),
    defaultValues: defaultIntegrationServiceFormValues,
  });

  const isDirty = form.formState.isDirty;

  useEffect(() => {
    if (isNew) {
      form.reset(defaultIntegrationServiceFormValues);
      setLoading(false);
      return;
    }

    if (!serviceId) return;

    setLoading(true);
    getIntegrationService(serviceId)
      .then((doc) => {
        setIsBuiltin(doc.is_builtin === 1);
        form.reset(mapDocToFormValues(doc));
      })
      .catch((error) => {
        toast.error(getFrappeErrorMessage(error) || 'Failed to load integration service');
        navigate('/integration-services');
      })
      .finally(() => setLoading(false));
  }, [serviceId, isNew, form, navigate]);

  const onSubmit = useCallback(
    async (values: IntegrationServiceFormValues) => {
      setSaving(true);
      try {
        const payload = mapFormToPayload(values);

        if (isNew) {
          const created = await createIntegrationService(payload);
          toast.success('Integration service created successfully');
          form.reset(mapDocToFormValues(created));
          navigate(`/integration-services/${encodeURIComponent(created.service_name)}`);
          return;
        }

        if (!serviceId) return;

        const updated = await updateIntegrationService(serviceId, payload);
        toast.success('Integration service updated successfully');
        form.reset(mapDocToFormValues(updated));

        if (updated.name && updated.name !== serviceId) {
          navigate(`/integration-services/${encodeURIComponent(updated.name)}`, { replace: true });
          return;
        }
      } catch (error) {
        toast.error(
          getFrappeErrorMessage(error) ||
            `Failed to ${isNew ? 'create' : 'update'} integration service`,
        );
      } finally {
        setSaving(false);
      }
    },
    [form, isNew, navigate, serviceId],
  );

  const handleFormSubmit = useMemo(
    () => createFormSubmitHandler(form, activeTab, tabFieldMapping, tabLabels, onSubmit),
    [form, activeTab, tabFieldMapping, tabLabels, onSubmit],
  );

  const showSaveButton = isNew || isDirty;

  useSaveShortcut({
    onSave: handleFormSubmit,
    enabled: showSaveButton,
    isSubmitting: saving,
  });

  const handleDelete = async () => {
    if (!serviceId || isNew) return;

    setDeleting(true);
    try {
      await deleteIntegrationService(serviceId);
      toast.success('Integration service deleted');
      navigate('/integration-services');
    } catch (error) {
      toast.error(getFrappeErrorMessage(error) || 'Failed to delete integration service');
    } finally {
      setDeleting(false);
      setDeleteDialogOpen(false);
    }
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="font-body text-steel-soft">Loading service...</div>
      </div>
    );
  }

  const title = form.watch('service_name') || serviceId || 'Integration Service';

  return (
    <div className="h-full overflow-auto">
      <div className="p-6 space-y-6 max-w-6xl mx-auto">
        <IntegrationServiceHeader
          title={title}
          isBuiltin={isBuiltin}
          isNew={isNew}
          showSaveButton={showSaveButton}
          saving={saving}
          deleting={deleting}
          canDelete={!isBuiltin}
          onSave={handleFormSubmit}
          onDelete={() => setDeleteDialogOpen(true)}
          onTitleChange={(value) => form.setValue('service_name', value, { shouldDirty: true })}
        />

        <Form {...form}>
          <form onSubmit={handleFormSubmit} className="space-y-6">
            <Tabs value={activeTab} onValueChange={handleTabChange}>
              <TabsList>
                {Object.entries(tabConfig).map(([key, config]) => (
                  <TabsTrigger key={key} value={key} disabled={config.disabled}>
                    {config.label}
                  </TabsTrigger>
                ))}
              </TabsList>

              <TabsContent value="general" className="space-y-4">
                <GeneralTab form={form} isNew={isNew} />
              </TabsContent>

              <TabsContent value="credentials" className="space-y-4">
                <CredentialsSchemaTab form={form} />
              </TabsContent>
            </Tabs>
          </form>
        </Form>

        <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete integration service?</AlertDialogTitle>
              <AlertDialogDescription>
                This will permanently delete &quot;{title}&quot;. Integration Settings linked to this
                service may fail if they still reference it.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel disabled={deleting}>Cancel</AlertDialogCancel>
              <AlertDialogAction
                onClick={handleDelete}
                disabled={deleting}
                className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              >
                {deleting ? 'Deleting...' : 'Delete'}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    </div>
  );
}

export default IntegrationServiceFormPage;
