import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { Copy, Download, ExternalLink, Loader2, RefreshCw } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  DEFAULT_PACKAGE_VERSION,
  buildPackageDownloadUrl,
  diagnoseTeams,
  errorText,
  findCheck,
  getTeamsSettings,
  isValidPackageVersion,
  parseTenantText,
  saveTeamsAllowedTenants,
  saveTeamsPackageVersion,
  type TeamsDiagnosis,
} from '@/services/teamsApi';
import { registerProviderPanel, type ProviderPanelProps } from './index';
import { TeamsCheckRow, TeamsStatusChips } from './TeamsDiagnosticsPanel';

const ENTRA_URL = 'https://entra.microsoft.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade';
const AZURE_BOT_URL = 'https://portal.azure.com/#create/Microsoft.AzureBot';
const TEAMS_ADMIN_URL = 'https://admin.teams.microsoft.com/policies/manage-apps';
const TEAMS_URL = 'https://teams.microsoft.com';
const WATCH_INTERVAL_MS = 5000;

export function TeamsSetupPanel({ gateway }: ProviderPanelProps) {
  const [diagnosis, setDiagnosis] = useState<TeamsDiagnosis | null>(null);
  const [testing, setTesting] = useState(false);
  const [testError, setTestError] = useState<string | null>(null);

  const [tenantText, setTenantText] = useState('');
  const [settingsLoading, setSettingsLoading] = useState(true);
  const [settingsError, setSettingsError] = useState<string | null>(null);
  const [savingTenants, setSavingTenants] = useState(false);
  const [tenantError, setTenantError] = useState<string | null>(null);

  const [version, setVersion] = useState(DEFAULT_PACKAGE_VERSION);

  const [watching, setWatching] = useState(false);
  const watchTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const runTest = useCallback(async () => {
    setTesting(true);
    setTestError(null);
    try {
      setDiagnosis(await diagnoseTeams(gateway.name));
    } catch (e) {
      setTestError(errorText(e, 'Could not check the Teams connection'));
    } finally {
      setTesting(false);
    }
  }, [gateway.name]);

  const loadSettings = useCallback(async () => {
    setSettingsLoading(true);
    setSettingsError(null);
    try {
      const settings = await getTeamsSettings(gateway.name);
      setTenantText((settings.allowed_tenant_list ?? []).join('\n'));
      if (settings.app_package_version) setVersion(settings.app_package_version);
    } catch (e) {
      setSettingsError(errorText(e, 'Could not load the Teams settings'));
    } finally {
      setSettingsLoading(false);
    }
  }, [gateway.name]);

  useEffect(() => {
    void runTest();
    void loadSettings();
  }, [runTest, loadSettings]);

  const stopWatching = useCallback(() => {
    if (watchTimer.current) clearInterval(watchTimer.current);
    watchTimer.current = null;
    setWatching(false);
  }, []);

  useEffect(() => stopWatching, [stopWatching]);

  const inboundSeen = findCheck(diagnosis, 'last_inbound')?.status === 'pass';

  useEffect(() => {
    if (inboundSeen && watching) stopWatching();
  }, [inboundSeen, watching, stopWatching]);

  const startWatching = useCallback(() => {
    setWatching(true);
    void runTest();
    watchTimer.current = setInterval(() => {
      diagnoseTeams(gateway.name)
        .then(setDiagnosis)
        .catch(() => {
          // keep the last good result; the admin can retry manually
        });
    }, WATCH_INTERVAL_MS);
  }, [gateway.name, runTest]);

  const endpoint = findCheck(diagnosis, 'messaging_endpoint')?.detail ?? '';

  const copyEndpoint = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(endpoint);
      toast.success('Messaging address copied');
    } catch {
      toast.error('Could not copy the messaging address');
    }
  }, [endpoint]);

  const parsed = parseTenantText(tenantText);

  const saveTenants = useCallback(async () => {
    if (parsed.invalid.length > 0) {
      setTenantError(`These lines are not valid directory IDs: ${parsed.invalid.join(', ')}`);
      return;
    }
    setSavingTenants(true);
    setTenantError(null);
    try {
      const saved = await saveTeamsAllowedTenants(gateway.name, parsed.tenants);
      setTenantText((saved.allowed_tenant_list ?? parsed.tenants).join('\n'));
      toast.success('Allowed organisations saved');
      void runTest();
    } catch (e) {
      setTenantError(errorText(e, 'Could not save the allowed organisations'));
    } finally {
      setSavingTenants(false);
    }
  }, [gateway.name, parsed.invalid, parsed.tenants, runTest]);

  const versionOk = isValidPackageVersion(version);

  const downloadPackage = useCallback(async () => {
    try {
      await saveTeamsPackageVersion(gateway.name, version);
    } catch {
      // the download does not depend on the saved note
    }
    window.location.assign(buildPackageDownloadUrl(gateway.name, version));
  }, [gateway.name, version]);

  const testChecks = diagnosis?.checks.filter((c) => ['credentials_present', 'token_acquisition'].includes(c.id)) ?? [];

  return (
    <div className="space-y-6">
      <TeamsStatusChips diagnosis={diagnosis} />

      <section className="space-y-2" aria-labelledby="teams-step-1">
        <p id="teams-step-1" className="text-sm font-medium">1. Create the Entra app and Azure Bot</p>
        <p className="text-sm text-muted-foreground">
          In Microsoft Entra, register a single-tenant app and create a client secret. Then create an Azure Bot that
          uses that app, turn on the Microsoft Teams channel, and set its messaging endpoint to this address.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <Input readOnly aria-label="Messaging address" value={endpoint} placeholder={testing ? 'Loading…' : 'Not available yet'} className="min-w-0 flex-1 font-mono text-xs" />
          <Button type="button" size="sm" variant="outline" onClick={copyEndpoint} disabled={!endpoint}>
            <Copy className="mr-1 h-3.5 w-3.5" /> Copy
          </Button>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" size="sm" variant="ghost" asChild>
            <a href={ENTRA_URL} target="_blank" rel="noreferrer">
              <ExternalLink className="mr-1 h-3.5 w-3.5" /> Open Microsoft Entra
            </a>
          </Button>
          <Button type="button" size="sm" variant="ghost" asChild>
            <a href={AZURE_BOT_URL} target="_blank" rel="noreferrer">
              <ExternalLink className="mr-1 h-3.5 w-3.5" /> Create Azure Bot
            </a>
          </Button>
        </div>
      </section>

      <section className="space-y-1" aria-labelledby="teams-step-2">
        <p id="teams-step-2" className="text-sm font-medium">2. Enter your app details</p>
        <p className="text-sm text-muted-foreground">
          Open the Credentials tab and enter the app (client) ID, the client secret and the directory (tenant) ID. Keys
          are never shown again after you save them.
        </p>
      </section>

      <section className="space-y-2" aria-labelledby="teams-step-3">
        <p id="teams-step-3" className="text-sm font-medium">3. Test the connection</p>
        <Button type="button" size="sm" onClick={runTest} disabled={testing}>
          {testing ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="mr-1 h-3.5 w-3.5" />}
          {testError ? 'Retry' : 'Test connection'}
        </Button>
        {testError && <p className="text-sm text-destructive">{testError}</p>}
        {testChecks.length > 0 && (
          <ul className="space-y-2" aria-label="Connection test results">
            {testChecks.map((c) => (
              <TeamsCheckRow key={c.id} check={c} />
            ))}
          </ul>
        )}
      </section>

      <section className="space-y-2" aria-labelledby="teams-step-4">
        <p id="teams-step-4" className="text-sm font-medium">4. Allowed organisations</p>
        <p className="text-sm text-muted-foreground">
          Your own organisation is always allowed. To let other organisations use the bot, enter their directory
          (tenant) IDs, one per line.
        </p>
        {settingsError && (
          <Alert variant="destructive">
            <AlertDescription className="flex flex-wrap items-center gap-2">
              {settingsError}
              <Button type="button" size="sm" variant="outline" onClick={loadSettings}>
                Retry
              </Button>
            </AlertDescription>
          </Alert>
        )}
        <Label htmlFor="teams-tenants" className="sr-only">Allowed directory IDs</Label>
        <Textarea
          id="teams-tenants"
          rows={4}
          className="font-mono text-xs"
          placeholder="00000000-0000-0000-0000-000000000000"
          value={tenantText}
          onChange={(e) => setTenantText(e.target.value)}
          disabled={settingsLoading || savingTenants}
          aria-invalid={parsed.invalid.length > 0}
        />
        {parsed.invalid.length > 0 && (
          <p className="text-sm text-destructive">Not a valid directory ID: {parsed.invalid.join(', ')}</p>
        )}
        <Button type="button" size="sm" onClick={saveTenants} disabled={savingTenants || settingsLoading || parsed.invalid.length > 0}>
          {savingTenants && <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />}
          Save organisations
        </Button>
        {tenantError && <p className="text-sm text-destructive">{tenantError}</p>}
      </section>

      <section className="space-y-2" aria-labelledby="teams-step-5">
        <p id="teams-step-5" className="text-sm font-medium">5. Download the Teams app package</p>
        <div className="flex flex-wrap items-end gap-2">
          <div className="space-y-1">
            <Label htmlFor="teams-package-version">Version</Label>
            <Input
              id="teams-package-version"
              className="w-32"
              value={version}
              onChange={(e) => setVersion(e.target.value)}
              aria-invalid={!versionOk}
            />
          </div>
          <Button type="button" size="sm" onClick={downloadPackage} disabled={!versionOk}>
            <Download className="mr-1 h-3.5 w-3.5" /> Download package
          </Button>
        </div>
        {!versionOk && <p className="text-sm text-destructive">Use a version like 1.0.0.</p>}
        <p className="text-sm text-muted-foreground">Raise the version each time you download a new package.</p>
      </section>

      <section className="space-y-2" aria-labelledby="teams-step-6">
        <p id="teams-step-6" className="text-sm font-medium">6. Upload it in Teams</p>
        <p className="text-sm text-muted-foreground">
          Organisation-wide: in the Teams admin center open Manage apps, choose Upload new app and select the package.
          Just for you: in Teams open Apps, choose Manage your apps, then Upload an app.
        </p>
        <div className="flex flex-wrap gap-2">
          <Button type="button" size="sm" variant="ghost" asChild>
            <a href={TEAMS_ADMIN_URL} target="_blank" rel="noreferrer">
              <ExternalLink className="mr-1 h-3.5 w-3.5" /> Teams admin center
            </a>
          </Button>
          <Button type="button" size="sm" variant="ghost" asChild>
            <a href={TEAMS_URL} target="_blank" rel="noreferrer">
              <ExternalLink className="mr-1 h-3.5 w-3.5" /> Open Teams
            </a>
          </Button>
        </div>
      </section>

      <section className="space-y-2" aria-labelledby="teams-step-7">
        <p id="teams-step-7" className="text-sm font-medium">7. Say hello to the bot</p>
        <p className="text-sm text-muted-foreground">
          In a personal chat with the app, send &quot;help&quot;. The last message line below turns green once Huf has
          received it.
        </p>
        <div className="flex flex-wrap gap-2">
          <Button type="button" size="sm" variant="outline" onClick={runTest} disabled={testing}>
            {testing ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="mr-1 h-3.5 w-3.5" />}
            Refresh
          </Button>
          <Button type="button" size="sm" variant="ghost" onClick={watching ? stopWatching : startWatching} disabled={inboundSeen}>
            {watching ? 'Stop watching' : 'Watch for the message'}
          </Button>
        </div>
        {(() => {
          const check = findCheck(diagnosis, 'last_inbound');
          return check ? <ul aria-live="polite"><TeamsCheckRow check={check} /></ul> : null;
        })()}
      </section>
    </div>
  );
}

registerProviderPanel('Microsoft Teams', { id: 'teams-setup', title: 'Teams setup', component: TeamsSetupPanel });
