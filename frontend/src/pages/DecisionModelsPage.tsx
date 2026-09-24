import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Cpu, Settings, Loader2, Plus, Zap, Star, Power } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { PageFrame } from '@/layouts/PageFrame';
import { ProviderModelTabs } from '@/components/settings/ProviderModelTabs';
import { FilterBar, GridView, EmptyState, ItemCard } from '@/components/dashboard';
import {
  DeploymentFields,
  deploymentDocToForm,
  emptyDeploymentFormData,
  getDeploymentDoc,
  saveDeployment,
  validateDeploymentForm,
  type DeploymentFormData,
} from '@/components/decision/DeploymentForm';
import {
  listDecisionModels,
  testDeployment,
  getSetupCatalog,
  setupDeployment,
  type DecisionDeployment,
  type SetupCatalogEntry,
} from '@/services/decisionApi';
import { getProviders } from '@/services/providerApi';
import type { AIProvider } from '@/types/agent.types';
import { call } from '@/lib/frappe-sdk';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { useSaveShortcut } from '@/hooks/useSaveShortcut';

/** One card per deployment, carrying the Decision Model it serves. */
interface DeploymentRow extends DecisionDeployment {
  decision_model_name: string;
}

type Health = 'healthy' | 'unhealthy' | 'unknown';

function healthOf(d: DecisionDeployment): Health {
  if (d.health_status === 'healthy' || d.health_status === 'ok') return 'healthy';
  if (d.health_status) return 'unhealthy';
  return 'unknown';
}

const catalogKey = (e: SetupCatalogEntry) => `${e.provider_brand}::${e.model_name}`;

export function DecisionModelsPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const [rows, setRows] = useState<DeploymentRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [providerFilter, setProviderFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [busy, setBusy] = useState<string | null>(null);

  // Configure dialog (edit an existing deployment)
  const [configureTarget, setConfigureTarget] = useState<DeploymentRow | null>(null);
  const [loadingDoc, setLoadingDoc] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formData, setFormData] = useState<DeploymentFormData>(emptyDeploymentFormData);

  // Add dialog (replaces the old System One wizard)
  const [addOpen, setAddOpen] = useState(false);
  const [catalog, setCatalog] = useState<SetupCatalogEntry[]>([]);
  const [providers, setProviders] = useState<AIProvider[]>([]);
  const [addEntryKey, setAddEntryKey] = useState('');
  const [addProvider, setAddProvider] = useState('');
  const [adding, setAdding] = useState(false);

  const loadRows = async () => {
    setLoading(true);
    try {
      const models = await listDecisionModels();
      setRows(
        models.flatMap((m) =>
          (m.deployments || []).map((d) => ({
            ...d,
            decision_model_name: m.display_name || m.model_name,
          })),
        ),
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadRows();
    getProviders()
      .then((data) => setProviders(Array.isArray(data) ? data : data.items))
      .catch((e) => console.error('Error fetching providers:', e));
  }, []);

  // `?setup=1` (older deep link to the wizard) now opens the Add dialog.
  useEffect(() => {
    if (searchParams.get('setup') === '1') {
      openAdd();
      setSearchParams({}, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const providerOptions = useMemo(
    () => Array.from(new Set(rows.map((r) => r.provider).filter(Boolean))).sort(),
    [rows],
  );

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rows.filter((r) => {
      if (providerFilter !== 'all' && r.provider !== providerFilter) return false;
      if (statusFilter === 'enabled' && !r.enabled) return false;
      if (statusFilter === 'disabled' && r.enabled) return false;
      if (statusFilter === 'unhealthy' && healthOf(r) !== 'unhealthy') return false;
      if (!q) return true;
      return [r.deployment_name, r.provider, r.provider_model_id, r.decision_model_name, r.name]
        .filter(Boolean)
        .some((v) => String(v).toLowerCase().includes(q));
    });
  }, [rows, search, providerFilter, statusFilter]);

  // ---- row actions -------------------------------------------------------

  const handleTest = async (d: DeploymentRow) => {
    setBusy(d.name);
    try {
      const result = await testDeployment(d.name);
      if (result.status === 'success') {
        toast.success(`Connection successful (${result.latency_ms}ms)`);
      } else {
        toast.error(`Connection failed: ${result.error_code || 'Unknown error'}`);
      }
      await loadRows();
    } catch {
      // testDeployment already surfaced the error
    } finally {
      setBusy(null);
    }
  };

  const setField = async (d: DeploymentRow, fieldname: Record<string, unknown>, ok: string) => {
    setBusy(d.name);
    try {
      await call.post('frappe.client.set_value', {
        doctype: 'Decision Deployment',
        name: d.name,
        fieldname,
      });
      toast.success(ok);
      await loadRows();
    } catch (e) {
      toast.error('Failed to update deployment', { description: getFrappeErrorMessage(e) });
    } finally {
      setBusy(null);
    }
  };

  // ---- configure dialog --------------------------------------------------

  const handleConfigure = async (d: DeploymentRow) => {
    setConfigureTarget(d);
    setLoadingDoc(true);
    try {
      setFormData(deploymentDocToForm(await getDeploymentDoc(d.name)));
    } catch (e) {
      toast.error('Failed to load deployment details');
      console.error(e);
    } finally {
      setLoadingDoc(false);
    }
  };

  const handleSave = async () => {
    if (!configureTarget) return;
    const invalid = validateDeploymentForm(formData);
    if (invalid) {
      toast.error(invalid);
      return;
    }
    setSaving(true);
    try {
      await saveDeployment(configureTarget.name, formData);
      toast.success('Deployment updated');
      setConfigureTarget(null);
      await loadRows();
    } catch (e) {
      toast.error('Failed to update deployment', { description: getFrappeErrorMessage(e) });
    } finally {
      setSaving(false);
    }
  };

  useSaveShortcut({
    onSave: handleSave,
    enabled: !!configureTarget && !loadingDoc,
    isSubmitting: saving,
    allowInDialog: true,
  });

  // ---- add dialog --------------------------------------------------------

  function openAdd() {
    setAddEntryKey('');
    setAddProvider('');
    setAddOpen(true);
    getSetupCatalog().then(setCatalog);
  }

  const addEntry = catalog.find((e) => catalogKey(e) === addEntryKey) || null;
  const brandProviders = addEntry
    ? providers.filter((p) => p.provider_brand === addEntry.provider_brand)
    : [];

  const handleAdd = async () => {
    if (!addEntry || !addProvider) {
      toast.error('Choose a model and a provider');
      return;
    }
    setAdding(true);
    try {
      const result = await setupDeployment(addProvider, addEntry.model_name);
      if (result.probe.status === 'success') {
        toast.success(`Deployment added and enabled (${result.probe.latency_ms}ms)`);
      } else {
        toast.warning(
          `Deployment added but disabled: connection test failed (${result.probe.error_code || 'unknown error'})`,
        );
      }
      setAddOpen(false);
      await loadRows();
    } catch {
      // setupDeployment already surfaced the error
    } finally {
      setAdding(false);
    }
  };

  const goToProviders = () => {
    setAddOpen(false);
    if (addProvider) {
      navigate(`/providers?configure=${encodeURIComponent(addProvider)}`);
    } else if (addEntry?.provider_brand === 'openrouter') {
      navigate('/providers?starter=openrouter');
    } else {
      navigate('/providers');
    }
  };

  const isFiltered = !!search || providerFilter !== 'all' || statusFilter !== 'all';

  return (
    <PageFrame
      title="Decision models"
      actions={
        <Button variant="display" size="sm" onClick={openAdd}>
          <Plus className="w-4 h-4 mr-2" />
          Add deployment
        </Button>
      }
      filters={
        <FilterBar
          searchPlaceholder="Search deployments..."
          searchValue={search}
          onSearchChange={setSearch}
          filters={[
            {
              label: 'Provider',
              value: providerFilter,
              options: [
                { label: 'All providers', value: 'all' },
                ...providerOptions.map((p) => ({ label: p, value: p })),
              ],
              onChange: setProviderFilter,
            },
            {
              label: 'Status',
              value: statusFilter,
              options: [
                { label: 'All statuses', value: 'all' },
                { label: 'Enabled', value: 'enabled' },
                { label: 'Disabled', value: 'disabled' },
                { label: 'Unhealthy', value: 'unhealthy' },
              ],
              onChange: setStatusFilter,
            },
          ]}
        />
      }
    >
      <ProviderModelTabs />
      <GridView
        items={filtered}
        columns={{ sm: 1, md: 2, lg: 3 }}
        loading={loading}
        emptyState={
          isFiltered ? (
            <EmptyState
              variant="no-results"
              icon={Cpu}
              title="No deployments found"
              filterTerm={search}
              secondaryAction={{
                label: 'Clear filters',
                onClick: () => {
                  setSearch('');
                  setProviderFilter('all');
                  setStatusFilter('all');
                },
              }}
            />
          ) : (
            <EmptyState
              variant="create"
              icon={Cpu}
              title="No decision deployments"
              description="Decision models answer bounded questions (pick one, yes/no, score) fast and cheaply. Add a deployment to connect one through a provider."
              action={{ label: 'Add deployment', onClick: openAdd }}
              secondaryAction={{
                label: 'Use a local rules/classifier backend',
                onClick: () => navigate('/decisions/new'),
              }}
            />
          )
        }
        keyExtractor={(d) => d.name}
        renderItem={(d) => {
          const health = healthOf(d);
          return (
            <ItemCard
              key={d.name}
              title={d.deployment_name || d.name}
              description={d.decision_model_name}
              icon={Cpu}
              status={{
                label: d.enabled ? 'Enabled' : 'Disabled',
                variant: d.enabled ? 'success' : 'secondary',
              }}
              metadata={[
                { label: 'Provider', value: d.provider || '-' },
                { label: 'Model', value: d.provider_model_id || '-' },
                { label: 'Priority', value: String(d.priority ?? 0) },
                ...(d.latency_budget_ms
                  ? [{ label: 'Latency budget', value: `${d.latency_budget_ms}ms` }]
                  : []),
              ]}
              badges={[
                ...(d.is_default_for_model ? [{ label: 'Default', variant: 'default' as const }] : []),
                { label: d.wire_protocol, variant: 'secondary' as const },
                ...(health !== 'unknown'
                  ? [{
                      label: health === 'healthy' ? 'Healthy' : 'Unhealthy',
                      variant: health === 'healthy' ? ('success' as const) : ('destructive' as const),
                    }]
                  : []),
              ]}
              actions={[
                { icon: Settings, label: 'Configure', onClick: () => handleConfigure(d), variant: 'ghost' },
                {
                  icon: Zap,
                  label: 'Test connection',
                  onClick: () => handleTest(d),
                  variant: 'ghost',
                },
              ]}
              menuActions={[
                {
                  icon: Power,
                  label: d.enabled ? 'Disable' : 'Enable',
                  onClick: () =>
                    setField(d, { enabled: d.enabled ? 0 : 1 }, d.enabled ? 'Deployment disabled' : 'Deployment enabled'),
                },
                ...(!d.is_default_for_model
                  ? [{
                      icon: Star,
                      label: 'Make default',
                      onClick: () => setField(d, { is_default_for_model: 1 }, 'Default deployment updated'),
                    }]
                  : []),
              ]}
              onClick={() => handleConfigure(d)}
            />
          );
        }}
      />
      {!loading && filtered.length > 0 && (
        <div className="text-center py-4 text-sm font-body text-steel">
          Showing {filtered.length} of {rows.length} deployments
        </div>
      )}

      {/* Configure an existing deployment */}
      <Dialog open={!!configureTarget} onOpenChange={(open) => !open && !saving && setConfigureTarget(null)}>
        <DialogContent className="sm:max-w-[520px] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Configure {configureTarget?.deployment_name || 'Deployment'}</DialogTitle>
            <DialogDescription>
              {configureTarget
                ? `${configureTarget.decision_model_name} via ${configureTarget.provider} · ${configureTarget.provider_model_id}`
                : 'Update deployment settings'}
            </DialogDescription>
          </DialogHeader>

          {loadingDoc ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-steel-soft" />
            </div>
          ) : (
            <>
              {configureTarget && (
                <div className="flex items-center justify-between rounded-lg border border-line px-3 py-2 text-sm mt-2">
                  <div>
                    <p className="text-ink">
                      Health:{' '}
                      {healthOf(configureTarget) === 'unknown'
                        ? 'not checked yet'
                        : healthOf(configureTarget)}
                    </p>
                    {configureTarget.last_healthcheck && (
                      <p className="text-xs text-steel-soft">Last checked {configureTarget.last_healthcheck}</p>
                    )}
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={busy === configureTarget.name}
                    onClick={async () => {
                      await handleTest(configureTarget);
                      setConfigureTarget(null);
                    }}
                  >
                    {busy === configureTarget.name ? (
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    ) : (
                      <Zap className="h-4 w-4 mr-2" />
                    )}
                    Test connection
                  </Button>
                </div>
              )}
              <DeploymentFields value={formData} onChange={setFormData} />
            </>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => setConfigureTarget(null)} disabled={saving || loadingDoc}>
              Cancel
            </Button>
            <Button onClick={handleSave} disabled={saving || loadingDoc}>
              {saving ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Saving...
                </>
              ) : (
                'Save'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Add a new deployment from the catalog */}
      <Dialog open={addOpen} onOpenChange={(open) => !adding && setAddOpen(open)}>
        <DialogContent className="sm:max-w-[520px] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Add deployment</DialogTitle>
            <DialogDescription>
              Connect a catalog decision model through one of your providers. A connection test runs
              on create; the deployment is enabled only if it passes.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="add_entry">
                Model <span className="text-destructive">*</span>
              </Label>
              <Select
                value={addEntryKey}
                onValueChange={(v) => {
                  setAddEntryKey(v);
                  const entry = catalog.find((e) => catalogKey(e) === v);
                  const match = entry ? providers.filter((p) => p.provider_brand === entry.provider_brand) : [];
                  setAddProvider(match.length === 1 ? match[0].name : '');
                }}
              >
                <SelectTrigger id="add_entry">
                  <SelectValue placeholder={catalog.length ? 'Select a model' : 'Loading catalog...'} />
                </SelectTrigger>
                <SelectContent>
                  {catalog.map((e) => (
                    <SelectItem key={catalogKey(e)} value={catalogKey(e)}>
                      {e.model_name} · {e.provider_brand}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {addEntry && (
                <p className="text-xs text-steel-soft">
                  {addEntry.canonical_model} ({addEntry.model_family}, {addEntry.model_class}) ·{' '}
                  {addEntry.wire_protocol} · {addEntry.endpoint_path}
                </p>
              )}
            </div>

            {addEntry && (
              <div className="space-y-2">
                <Label htmlFor="add_provider">
                  Provider <span className="text-destructive">*</span>
                </Label>
                {brandProviders.length > 0 ? (
                  <Select value={addProvider} onValueChange={setAddProvider}>
                    <SelectTrigger id="add_provider">
                      <SelectValue placeholder="Select a provider" />
                    </SelectTrigger>
                    <SelectContent>
                      {brandProviders.map((p) => (
                        <SelectItem key={p.name} value={p.name}>
                          {p.provider_name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <p className="text-sm text-steel">
                    No {addEntry.provider_brand} provider is set up yet.
                  </p>
                )}
                <p className="text-xs text-steel-soft">
                  {addEntry.provider_ready
                    ? 'Providers and API keys are managed on the Providers page.'
                    : `A ${addEntry.provider_brand} provider needs an API key before this can connect.`}{' '}
                  <button type="button" className="underline hover:text-ink" onClick={goToProviders}>
                    {brandProviders.length > 0 ? 'Manage provider' : 'Set up provider'}
                  </button>
                </p>
              </div>
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setAddOpen(false)} disabled={adding}>
              Cancel
            </Button>
            <Button onClick={handleAdd} disabled={adding || !addEntry || !addProvider}>
              {adding ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Adding...
                </>
              ) : (
                'Add & test'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageFrame>
  );
}
