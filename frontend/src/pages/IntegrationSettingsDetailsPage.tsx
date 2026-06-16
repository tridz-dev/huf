import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
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
import { IntegrationHeader } from '@/components/integrations/IntegrationHeader';
import { GeneralTab } from '@/components/integrations/GeneralTab';
import { CredentialsTab } from '@/components/integrations/CredentialsTab';
import { RecipientsTab } from '@/components/integrations/RecipientsTab';
import { TelegramTab } from '@/components/integrations/TelegramTab';
import { integrationFormSchema, type IntegrationFormValues } from '@/components/integrations/types';
import {
  createIntegrationSetting,
  deleteIntegrationSetting,
  getIntegrationService,
  getIntegrationSetting,
  setupTelegramWebhook,
  updateIntegrationSetting,
} from '@/services/integrationApi';
import { getAgents } from '@/services/agentApi';
import {
  buildCredentialsPayload,
  parseRequiredCredentials,
  type CredentialSchemaItem,
  type IntegrationSettingsDoc,
} from '@/types/integration.types';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { createFormSubmitHandler, type TabFieldMapping } from '@/utils/formValidation';

export function IntegrationSettingsDetailsPage() {
  const { settingId } = useParams<{ settingId: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const isNew = settingId === 'new';
  const initialService = searchParams.get('service') || '';

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [settingUpWebhook, setSettingUpWebhook] = useState(false);
  const [credentialSchema, setCredentialSchema] = useState<CredentialSchemaItem[]>([]);
  const [agents, setAgents] = useState<Array<{ name: string; agent_name: string }>>([]);
  const [docMeta, setDocMeta] = useState({
    lastUsed: undefined as string | undefined,
    lastError: undefined as string | undefined,
    webhookUrl: undefined as string | undefined,
    webhookStatus: undefined as string | undefined,
    lastWebhookSetup: undefined as string | undefined,
  });

  const form = useForm<IntegrationFormValues>({
    resolver: zodResolver(integrationFormSchema),
    defaultValues: {
      service: initialService,
      is_active: true,
      is_default: false,
      credentialValues: {},
      recipients: [],
      telegram_agent: '',
      telegram_auto_setup_webhook: true,
    },
  });

  const watchService = form.watch('service');
  const watchIsActive = form.watch('is_active');
  const watchIsDefault = form.watch('is_default');
  const isDirty = form.formState.isDirty;
  const isTelegram = (isNew ? initialService : watchService) === 'telegram';

  const tabConfig = useMemo(() => {
    const base = {
      general: {
        label: 'General',
        fields: ['service', 'is_active', 'is_default'],
        default: true,
        disabled: false,
      },
      credentials: {
        label: 'Credentials',
        fields: ['credentialValues'],
        default: false,
        disabled: false,
      },
      recipients: {
        label: 'Recipients',
        fields: ['recipients'],
        default: false,
        disabled: false,
      },
    };

    if ((isNew ? initialService : watchService) === 'telegram') {
      return {
        ...base,
        telegram: {
          label: 'Telegram',
          fields: ['telegram_agent', 'telegram_auto_setup_webhook'],
          default: false,
          disabled: isNew,
        },
      };
    }

    return base;
  }, [isNew, initialService, watchService]);

  const validTabs = useMemo(() => Object.keys(tabConfig), [tabConfig]);
  const defaultTab = useMemo(
    () => Object.entries(tabConfig).find(([, config]) => config.default)?.[0] || validTabs[0],
    [tabConfig, validTabs],
  );
  const tabFieldMapping: TabFieldMapping = useMemo(
    () => Object.fromEntries(
      Object.entries(tabConfig).map(([key, config]) => [key, [...config.fields]]),
    ),
    [tabConfig],
  );
  const tabLabels = useMemo(
    () => Object.fromEntries(
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
      window.history.replaceState(null, '', window.location.pathname + window.location.search);
    } else {
      window.location.hash = value;
    }
  };

  const loadServiceSchema = useCallback(async (serviceName: string) => {
    if (!serviceName) return;
    try {
      const serviceDoc = await getIntegrationService(serviceName);
      setCredentialSchema(parseRequiredCredentials(serviceDoc.required_credentials));
    } catch (error) {
      toast.error(getFrappeErrorMessage(error) || 'Failed to load service schema');
    }
  }, []);

  useEffect(() => {
    if (isNew) {
      if (!initialService) {
        toast.error('Please select a service from the catalog');
        navigate('/integrations');
        return;
      }
      form.reset({
        service: initialService,
        is_active: true,
        is_default: false,
        credentialValues: {},
        recipients: [],
        telegram_agent: '',
        telegram_auto_setup_webhook: true,
      });
      loadServiceSchema(initialService).finally(() => setLoading(false));
      return;
    }

    if (!settingId) return;

    getIntegrationSetting(settingId)
      .then((data) => {
        const schemaPromise = loadServiceSchema(data.service);
        const credValues: Record<string, string> = {};
        for (const cred of data.credentials ?? []) {
          credValues[cred.key] = '';
        }

        form.reset({
          service: data.service,
          is_active: data.is_active === 1,
          is_default: data.is_default === 1,
          credentialValues: credValues,
          recipients: (data.recipients ?? []).map((r) => ({
            name: r.name,
            recipient_name: r.recipient_name,
            recipient_id: r.recipient_id,
            user: r.user || '',
          })),
          telegram_agent: data.telegram_agent || '',
          telegram_auto_setup_webhook: data.telegram_auto_setup_webhook !== 0,
        });

        setDocMeta({
          lastUsed: data.last_used,
          lastError: data.last_error,
          webhookUrl: data.telegram_webhook_url,
          webhookStatus: data.telegram_webhook_status,
          lastWebhookSetup: data.telegram_last_webhook_setup,
        });

        return schemaPromise;
      })
      .catch((error) => {
        toast.error(getFrappeErrorMessage(error) || 'Failed to load integration');
      })
      .finally(() => setLoading(false));
  }, [isNew, initialService, settingId, form, navigate, loadServiceSchema]);

  useEffect(() => {
    if (isTelegram) {
      getAgents().then((result) => {
        const list = Array.isArray(result) ? result : result.items;
        setAgents(list.map((a) => ({ name: a.name, agent_name: a.agent_name || a.name })));
      }).catch(() => {
        // Agents optional for display
      });
    }
  }, [isTelegram]);

  const validateCredentials = (
    values: IntegrationFormValues,
    schema: CredentialSchemaItem[],
    creating: boolean,
  ): boolean => {
    if (!creating) return true;

    for (const item of schema) {
      if (item.required && !values.credentialValues[item.key]?.trim()) {
        toast.error(`${item.label} is required`);
        return false;
      }
    }
    return true;
  };

  const onSubmit = useCallback(async (values: IntegrationFormValues) => {
    if (!validateCredentials(values, credentialSchema, isNew)) {
      return;
    }

    setSaving(true);
    try {
      let existingCredentials;
      if (!isNew && settingId) {
        const existing = await getIntegrationSetting(settingId);
        existingCredentials = existing.credentials;
      }

      const credentials = buildCredentialsPayload(
        credentialSchema,
        values.credentialValues,
        existingCredentials,
        isNew,
      );

      const payload: Partial<IntegrationSettingsDoc> = {
        service: values.service,
        is_active: values.is_active ? 1 : 0,
        is_default: values.is_default ? 1 : 0,
        credentials,
        recipients: values.recipients.map((r) => ({
          ...(r.name ? { name: r.name } : {}),
          recipient_name: r.recipient_name,
          recipient_id: r.recipient_id,
          user: r.user || undefined,
        })),
        ...(values.service === 'telegram'
          ? {
              telegram_agent: values.telegram_agent || undefined,
              telegram_auto_setup_webhook: values.telegram_auto_setup_webhook ? 1 : 0,
            }
          : {}),
      };

      if (isNew) {
        const created = await createIntegrationSetting(payload);
        toast.success('Integration created successfully');
        navigate(`/integrations/${encodeURIComponent(created.name)}`, { replace: true });
      } else if (settingId) {
        const updated = await updateIntegrationSetting(settingId, payload);
        toast.success('Integration updated successfully');

        const credValues: Record<string, string> = {};
        for (const item of credentialSchema) {
          credValues[item.key] = '';
        }

        form.reset({
          ...values,
          credentialValues: credValues,
        });

        setDocMeta({
          lastUsed: updated.last_used,
          lastError: updated.last_error,
          webhookUrl: updated.telegram_webhook_url,
          webhookStatus: updated.telegram_webhook_status,
          lastWebhookSetup: updated.telegram_last_webhook_setup,
        });
      }
    } catch (error) {
      toast.error(getFrappeErrorMessage(error) || 'Failed to save integration');
    } finally {
      setSaving(false);
    }
  }, [credentialSchema, form, isNew, navigate, settingId]);

  const handleFormSubmit = useMemo(
    () => createFormSubmitHandler(form, activeTab, tabFieldMapping, tabLabels, onSubmit),
    [form, activeTab, tabFieldMapping, tabLabels, onSubmit],
  );

  const handleDelete = async () => {
    if (!settingId || isNew) return;

    setDeleting(true);
    try {
      await deleteIntegrationSetting(settingId);
      toast.success('Integration deleted');
      navigate('/integrations');
    } catch (error) {
      toast.error(getFrappeErrorMessage(error) || 'Failed to delete integration');
    } finally {
      setDeleting(false);
      setDeleteDialogOpen(false);
    }
  };

  const handleSetupWebhook = async () => {
    if (!settingId || isNew) {
      toast.error('Save the integration before setting up the webhook');
      return;
    }

    setSettingUpWebhook(true);
    try {
      const result = await setupTelegramWebhook(settingId);
      toast.success(result.status || 'Webhook setup completed');
      const refreshed = await getIntegrationSetting(settingId);
      setDocMeta((prev) => ({
        ...prev,
        webhookUrl: refreshed.telegram_webhook_url,
        webhookStatus: refreshed.telegram_webhook_status,
        lastWebhookSetup: refreshed.telegram_last_webhook_setup,
      }));
    } catch (error) {
      toast.error(getFrappeErrorMessage(error) || 'Failed to setup webhook');
    } finally {
      setSettingUpWebhook(false);
    }
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-muted-foreground">Loading integration...</div>
      </div>
    );
  }

  const displayService = watchService || initialService;
  const tabCols = validTabs.length;

  return (
    <div className="h-full overflow-auto">
      <div className="p-6 space-y-6 max-w-6xl mx-auto">
        <IntegrationHeader
          title={settingId && !isNew ? settingId : ''}
          service={displayService}
          isActive={watchIsActive}
          isDefault={watchIsDefault}
          isNew={isNew}
          showSaveButton={isNew || isDirty}
          saving={saving}
          deleting={deleting}
          onSave={handleFormSubmit}
          onDelete={!isNew ? () => setDeleteDialogOpen(true) : undefined}
        />

        <Form {...form}>
          <form onSubmit={handleFormSubmit} className="space-y-6">
            <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">
              <TabsList className={`grid w-full grid-cols-${tabCols}`} style={{ gridTemplateColumns: `repeat(${tabCols}, minmax(0, 1fr))` }}>
                {Object.entries(tabConfig).map(([tabKey, config]) => (
                  <TabsTrigger key={tabKey} value={tabKey} disabled={config.disabled}>
                    {config.label}
                  </TabsTrigger>
                ))}
              </TabsList>

              <TabsContent value="general" className="space-y-4">
                <GeneralTab
                  form={form}
                  isNew={isNew}
                  lastUsed={docMeta.lastUsed}
                  lastError={docMeta.lastError}
                />
              </TabsContent>

              <TabsContent value="credentials" className="space-y-4">
                <CredentialsTab form={form} schema={credentialSchema} isNew={isNew} />
              </TabsContent>

              <TabsContent value="recipients" className="space-y-4">
                <RecipientsTab form={form} />
              </TabsContent>

              {'telegram' in tabConfig && (
                <TabsContent value="telegram" className="space-y-4">
                  <TelegramTab
                    form={form}
                    agents={agents}
                    webhookUrl={docMeta.webhookUrl}
                    webhookStatus={docMeta.webhookStatus}
                    lastWebhookSetup={docMeta.lastWebhookSetup}
                    settingUpWebhook={settingUpWebhook}
                    onSetupWebhook={handleSetupWebhook}
                  />
                </TabsContent>
              )}
            </Tabs>
          </form>
        </Form>
      </div>

      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete integration?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently remove &quot;{settingId}&quot; and its stored credentials.
              Agents using this integration may fail until a replacement is configured.
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
  );
}

export default IntegrationSettingsDetailsPage;
