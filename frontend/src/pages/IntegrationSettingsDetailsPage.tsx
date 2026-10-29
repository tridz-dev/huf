import { useCallback, useEffect, useMemo, useState } from 'react';
import { Bot, Loader2, PlugZap } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { toast } from 'sonner';
import { Form } from '@/components/ui/form';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { DeleteSettingDialog } from './integration-settings/DeleteSettingDialog';
import { IntegrationHeader } from '@/components/integrations/IntegrationHeader';
import { AddIntegrationToAgentModal } from '@/components/integrations/AddIntegrationToAgentModal';
import { ConnectChannelAgentModal } from '@/components/integrations/ConnectChannelAgentModal';
import { CredentialsSection } from '@/components/integrations/connection/CredentialsSection';
import { OptionsCard } from '@/components/integrations/connection/OptionsCard';
import { ConnectionStatusLine } from '@/components/integrations/connection/ConnectionStatusLine';
import { useIntegrationTabs } from '@/components/integrations/connection/useIntegrationTabs';
import { metaFrom, useConnectionTest, type ConnectionMeta } from '@/components/integrations/connection/useConnectionTest';
import { IntegrationSetupGuide } from '@/components/integrations/IntegrationSetupGuide';
import { RecipientsTab } from '@/components/integrations/RecipientsTab';
import { ChannelTab } from '@/components/integrations/ChannelTab';
import { integrationFormSchema, type IntegrationFormValues } from '@/components/integrations/types';
import {
  createIntegrationSetting,
  deleteIntegrationSetting,
  clearIntegrationError,
  getIntegrationService,
  getIntegrationSetting,
  updateIntegrationSetting,
} from '@/services/integrationApi';
import { getServiceIdentity } from '@/data/serviceIdentity';
import { deriveStatus, integrationHealth, integrationTitle, isTestable, plainProblem } from '@/lib/integrations/health';
import {
  buildCredentialsPayload,
  parseRequiredCredentials,
  type CredentialSchemaItem,
  type IntegrationSettingsDoc,
} from '@/types/integration.types';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { createFormSubmitHandler } from '@/utils/formValidation';
import { useSaveShortcut } from '@/hooks/useSaveShortcut';

interface IntegrationSettingsDetailsPageProps {
  /**
   * Which UI surface this record belongs to — determined by the wrapper that
   * renders this page (IntegrationSettingsDetailsPageWrapper for /integrations,
   * GatewayDetailsPageWrapper for /gateways). Passed explicitly rather than
   * looked up async via getServiceSurface() so the very first render (and the
   * post-save/-delete navigation) never races a not-yet-loaded surface cache.
   */
  surface?: 'Integration' | 'Gateway';
}

export function IntegrationSettingsDetailsPage({
  surface = 'Integration',
}: IntegrationSettingsDetailsPageProps = {}) {
  const { settingId } = useParams<{ settingId: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const isNew = settingId === 'new';
  const initialService = searchParams.get('service') || '';
  const listRoute = surface === 'Gateway' ? '/gateways' : '/integrations';
  const noun = surface === 'Gateway' ? 'channel' : 'integration';
  const nounTitle = surface === 'Gateway' ? 'Channel' : 'Integration';

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [addToAgentOpen, setAddToAgentOpen] = useState(false);
  // Bumped after an agent is connected so the Channel tab reloads its gateway.
  const [channelVersion, setChannelVersion] = useState(0);
  const [credentialSchema, setCredentialSchema] = useState<CredentialSchemaItem[]>([]);
  const [serviceCategory, setServiceCategory] = useState<string>('');
  const [serviceSurface, setServiceSurface] = useState<string>('');
  const [docMeta, setDocMeta] = useState<ConnectionMeta>(() => metaFrom({}));
  const [savedKeys, setSavedKeys] = useState<Set<string>>(new Set());

  const form = useForm<IntegrationFormValues>({
    resolver: zodResolver(integrationFormSchema),
    defaultValues: {
      service: initialService,
      display_label: '',
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
  const watchCredentials = form.watch('credentialValues');
  const isDirty = form.formState.isDirty;

  const { tabConfig, validTabs, tabFieldMapping, tabLabels, activeTab, setActiveTab, handleTabChange } = useIntegrationTabs(
    serviceCategory,
    surface,
  );

  const loadServiceSchema = useCallback(async (serviceName: string) => {
    if (!serviceName) return;
    try {
      const serviceDoc = await getIntegrationService(serviceName);
      setCredentialSchema(parseRequiredCredentials(serviceDoc.required_credentials));
      setServiceCategory(serviceDoc.category || '');
      setServiceSurface(serviceDoc.surface || 'Integration');
    } catch (error) {
      toast.error(getFrappeErrorMessage(error) || 'Failed to load service schema');
    }
  }, []);

  useEffect(() => {
    if (isNew) {
      if (!initialService) {
        toast.error('Please select a service from the catalog');
        navigate(listRoute);
        return;
      }
      form.reset({
        service: initialService,
        display_label: '',
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
          display_label: data.display_label ?? '',
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

        setSavedKeys(new Set((data.credentials ?? []).filter((c) => Boolean(c.value)).map((c) => c.key)));
        setDocMeta(metaFrom(data));
        setLive(null);

        return schemaPromise;
      })
      .catch((error) => {
        toast.error(getFrappeErrorMessage(error) || `Failed to load ${noun}`);
      })
      .finally(() => setLoading(false));
  }, [isNew, initialService, settingId, form, navigate, loadServiceSchema, listRoute, noun]);

  const { testing, live, setLive, runTest } = useConnectionTest({
    form,
    isNew,
    settingId,
    ready: !loading && Boolean(serviceSurface),
    setDocMeta,
  });

  const validateCredentials = (
    values: IntegrationFormValues,
    schema: CredentialSchemaItem[],
    creating: boolean,
  ): boolean => {
    if (!creating) return true;

    for (const item of schema) {
      if (item.required && !values.credentialValues[item.key]?.trim()) {
        form.setError(`credentialValues.${item.key}` as `credentialValues.${string}`, { message: `${item.label} is required` });
        form.setFocus(`credentialValues.${item.key}` as `credentialValues.${string}`);
        toast.error(`${item.label} is required`);
        return false;
      }
    }
    return true;
  };

  const onSubmit = useCallback(async (values: IntegrationFormValues) => {
    setLive(null);
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
        display_label: (values.display_label ?? '').trim(),
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
        toast.success(`${nounTitle} created successfully`);
        navigate(`${listRoute}/${encodeURIComponent(created.name)}`, { replace: true, state: { autoTest: true } });
      } else if (settingId) {
        const updated = await updateIntegrationSetting(settingId, payload);
        toast.success(`${nounTitle} updated successfully`);

        const credValues: Record<string, string> = {};
        for (const item of credentialSchema) {
          credValues[item.key] = '';
        }

        form.reset({
          ...values,
          credentialValues: credValues,
        });

        setDocMeta(metaFrom(updated));
        const typedKeys = Object.entries(values.credentialValues ?? {}).filter(([, v]) => (v ?? '').trim() !== '').map(([k]) => k);
        if (typedKeys.length) {
          setSavedKeys((prev) => new Set([...prev, ...typedKeys]));
          // New credentials: check them straight away so the page never shows an old answer for them.
          if (isTestable(values.service)) void runTest();
        }
      }
    } catch (error) {
      toast.error(getFrappeErrorMessage(error) || `Failed to save ${noun}`);
    } finally {
      setSaving(false);
    }
  }, [credentialSchema, form, isNew, navigate, settingId, listRoute, noun, nounTitle, runTest]);

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
    if (!settingId || isNew) return;

    setDeleting(true);
    try {
      await deleteIntegrationSetting(settingId);
      toast.success(`${nounTitle} deleted`);
      navigate(listRoute);
    } catch (error) {
      toast.error(getFrappeErrorMessage(error) || `Failed to delete ${noun}`);
    } finally {
      setDeleting(false);
      setDeleteDialogOpen(false);
    }
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="font-body text-steel-soft">Loading {noun}...</div>
      </div>
    );
  }

  const displayService = watchService || initialService;
  const serviceTitle = getServiceIdentity(displayService).title;
  const showGatewayHint = surface === 'Integration' && !isNew && serviceSurface === 'Gateway';
  // Messaging channels connect an agent as the one that answers; other integrations attach tools.
  const isChannel = serviceSurface === 'Gateway' && Boolean(settingId) && !isNew;
  const tabCols = validTabs.length;
  const testable = isTestable(displayService);
  const hasTyped = Object.values(watchCredentials ?? {}).some((v) => typeof v === 'string' && v.trim() !== '');
  const pageTitle = isNew
    ? `New ${serviceTitle} ${noun}`
    : integrationTitle({ service: displayService, display_label: docMeta.displayLabel, account_label: docMeta.accountLabel });

  const savedDoc = {
    service: displayService,
    // An inactive connection that was tested still shows what the test said; "Switched off" is in the subtitle.
    is_active: (watchIsActive || docMeta.testStatus ? 1 : 0) as 0 | 1,
    last_error: docMeta.lastError,
    last_test_status: docMeta.testStatus,
    last_test_message: docMeta.testMessage,
    account_label: docMeta.accountLabel,
  };
  const { health, fixLabel } = deriveStatus(savedDoc, live, isNew);

  const openCredentials = () => {
    setActiveTab('connection');
    requestAnimationFrame(() => {
      document.getElementById('integration-credentials')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      const keys = credentialSchema.map((item) => item.key);
      const first = keys.find((k) => !savedKeys.has(k)) ?? keys[0];
      if (first) form.setFocus(`credentialValues.${first}` as `credentialValues.${string}`);
    });
  };

  const dismissProblem = async () => {
    if (!settingId) return;
    try {
      await clearIntegrationError(settingId);
      setDocMeta((prev) => ({ ...prev, lastError: undefined }));
    } catch (error) {
      toast.error(getFrappeErrorMessage(error) || 'Could not clear the message');
    }
  };

  const statusLine =
    health || testing ? (
      <ConnectionStatusLine
        health={health ?? integrationHealth({ ...savedDoc, last_test_status: '' })}
        checkedAt={live ? undefined : docMeta.testAt}
        unsaved={live?.unsaved}
        testing={testing}
        fixLabel={fixLabel}
        onFix={openCredentials}
        lastProblem={plainProblem(docMeta.lastError) || undefined}
        onDismissProblem={dismissProblem}
      />
    ) : null;

  return (
    <div className="h-full overflow-auto">
      <div className="p-6 space-y-6 max-w-6xl mx-auto">
        <IntegrationHeader
          title={pageTitle}
          subtitle={isNew ? undefined : [pageTitle.startsWith(serviceTitle) ? '' : serviceTitle, watchIsActive ? '' : 'Switched off', watchIsDefault ? 'Used by default' : ''].filter(Boolean).join(' · ') || undefined}
          isNew={isNew}
          showSaveButton={showSaveButton}
          saving={saving}
          deleting={deleting}
          onSave={handleFormSubmit}
          onDelete={!isNew ? () => setDeleteDialogOpen(true) : undefined}
          status={statusLine}
        >
          {testable && (
            <Button
              variant="outline"
              size="sm"
              type="button"
              onClick={() => void runTest()}
              disabled={testing || (isNew && !hasTyped)}
              title={isNew && !hasTyped ? 'Enter your credentials first' : undefined}
              data-testid="integration-test-connection"
            >
              {testing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <PlugZap className="mr-2 h-4 w-4" />}
              Test connection
            </Button>
          )}
          {!isNew && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setAddToAgentOpen(true)}
              type="button"
              data-testid="integration-use-in-agent"
            >
              <Bot className="w-4 h-4 mr-2" />
              Use in agent
            </Button>
          )}
        </IntegrationHeader>

        <Form {...form}>
          <form onSubmit={handleFormSubmit} className="space-y-6">
            <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">
              {tabCols > 1 && (
                <TabsList layout="grid" cols={tabCols}>
                  {Object.entries(tabConfig).map(([tabKey, config]) => (
                    <TabsTrigger key={tabKey} value={tabKey} disabled={config.disabled}>
                      {config.label}
                    </TabsTrigger>
                  ))}
                </TabsList>
              )}

              <TabsContent value="connection" className="space-y-4">
                <CredentialsSection form={form} schema={credentialSchema} isNew={isNew} savedKeys={savedKeys} />
                <IntegrationSetupGuide service={displayService} />
                <OptionsCard form={form} />
                {showGatewayHint && (
                  <div className="flex flex-col gap-2 rounded-md border bg-muted/40 p-3 sm:flex-row sm:items-center sm:justify-between">
                    <p className="text-sm text-muted-foreground">
                      To receive {serviceTitle} messages in Huf, connect it to a gateway.
                    </p>
                    <Button type="button" variant="outline" size="sm" onClick={() => navigate('/gateways')}>
                      Go to Gateways
                    </Button>
                  </div>
                )}
              </TabsContent>

              <TabsContent value="recipients" className="space-y-4">
                <RecipientsTab form={form} service={displayService} settingId={settingId && !isNew ? settingId : undefined} />
              </TabsContent>

              {'channel' in tabConfig && (
                <TabsContent value="channel" className="space-y-4">
                  <ChannelTab
                    key={channelVersion}
                    settingId={settingId && !isNew ? settingId : undefined}
                    isNew={isNew}
                  />
                </TabsContent>
              )}
            </Tabs>
          </form>
        </Form>
      </div>

      <DeleteSettingDialog
        open={deleteDialogOpen}
        onOpenChange={setDeleteDialogOpen}
        noun={noun}
        settingId={isNew ? settingId : pageTitle}
        deleting={deleting}
        onConfirm={handleDelete}
      />

      {isChannel && settingId ? (
        <ConnectChannelAgentModal
          open={addToAgentOpen}
          onOpenChange={setAddToAgentOpen}
          integrationName={settingId}
          onConnected={() => setChannelVersion((v) => v + 1)}
        />
      ) : (
        <AddIntegrationToAgentModal
          open={addToAgentOpen}
          onOpenChange={setAddToAgentOpen}
          service={displayService}
          integrationName={settingId && !isNew ? settingId : undefined}
        />
      )}
    </div>
  );
}

export default IntegrationSettingsDetailsPage;
