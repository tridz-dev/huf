import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { toast } from 'sonner';
import { Form, FormField, FormItem, FormLabel, FormControl, FormDescription, FormMessage } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { StatusDot } from '@/components/dashboard';
import { Save, Trash2, Cpu, Loader2, Play, ShieldCheck, LogOut, RefreshCw } from 'lucide-react';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import {
  createSubscriptionRuntime,
  deleteSubscriptionRuntime,
  getSubscriptionRuntime,
  logoutSubscriptionRuntime,
  reauthenticateSubscriptionRuntime,
  testSubscriptionRuntimeConnection,
  updateSubscriptionRuntime,
  type SubscriptionAuthChallenge,
  type SubscriptionRuntimeDoc,
  type SubscriptionRuntimeProbeResult,
} from '@/services/subscriptionRuntimeApi';
import { getSSHConnections, type SSHConnectionDoc } from '@/services/sshConnectionApi';
import { InlineEditName } from '@/components/common/InlineEditName';

const subscriptionRuntimeSchema = z.object({
  runtime_name: z.string().min(1, 'Runtime name is required'),
  enabled: z.boolean().default(true),
  provider_family: z.enum(['Claude', 'Codex', 'Gemini']),
  cli_type: z.string().optional(),
  cli_path: z.string().optional(),
  transport_type: z.enum(['Local', 'Docker', 'SSH']),
  working_directory: z.string().optional(),
  ssh_connection: z.string().optional(),
  docker_container: z.string().optional(),
  docker_context: z.string().optional(),
  docker_workdir: z.string().optional(),
  timeout_seconds: z.coerce.number().min(1).default(120),
  max_output_bytes: z.coerce.number().min(1).default(1048576),
  owner_user: z.string().optional(),
  tenancy_policy: z.enum(['owner_only', 'explicit_users', 'explicit_roles', 'system_managed_shared']),
  allowed_users_json: z.string().optional(),
  allowed_roles_json: z.string().optional(),
});

type SubscriptionRuntimeFormValues = z.infer<typeof subscriptionRuntimeSchema>;

const AUTH_STATUS_LABELS: Record<string, string> = {
  unknown: 'Unknown',
  ready: 'Ready',
  required: 'Required',
  waiting_user: 'Waiting on you',
  verifying: 'Verifying',
  failed: 'Failed',
};

export function SubscriptionRuntimeFormPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const isNew = id === 'new';
  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [testing, setTesting] = useState(false);
  const [reauthenticating, setReauthenticating] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const [testResult, setTestResult] = useState<SubscriptionRuntimeProbeResult | null>(null);
  const [authChallenge, setAuthChallenge] = useState<SubscriptionAuthChallenge | null>(null);
  const [runtimeDoc, setRuntimeDoc] = useState<SubscriptionRuntimeDoc | null>(null);
  const [sshConnections, setSshConnections] = useState<SSHConnectionDoc[]>([]);

  const form = useForm<SubscriptionRuntimeFormValues>({
    resolver: zodResolver(subscriptionRuntimeSchema),
    defaultValues: {
      runtime_name: '',
      enabled: true,
      provider_family: 'Claude',
      cli_type: '',
      cli_path: '',
      transport_type: 'Local',
      working_directory: '',
      ssh_connection: '',
      docker_container: '',
      docker_context: '',
      docker_workdir: '',
      timeout_seconds: 120,
      max_output_bytes: 1048576,
      owner_user: '',
      tenancy_policy: 'owner_only',
      allowed_users_json: '',
      allowed_roles_json: '',
    },
  });

  const watchTransportType = form.watch('transport_type');
  const watchTenancyPolicy = form.watch('tenancy_policy');

  useEffect(() => {
    let cancelled = false;
    getSSHConnections({ limit: 100 })
      .then((response) => {
        if (cancelled) return;
        const items = Array.isArray(response) ? response : response.items;
        setSshConnections(items);
      })
      .catch(() => {
        // Non-fatal: the SSH connection select will just be empty.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (isNew) {
      setLoading(false);
      return;
    }

    let cancelled = false;
    const loadRuntime = async () => {
      try {
        const doc = await getSubscriptionRuntime(id!);
        if (cancelled) return;

        setRuntimeDoc(doc);
        form.reset({
          runtime_name: doc.runtime_name || doc.name,
          enabled: doc.enabled === 1,
          provider_family: doc.provider_family,
          cli_type: doc.cli_type || '',
          cli_path: doc.cli_path || '',
          transport_type: doc.transport_type,
          working_directory: doc.working_directory || '',
          ssh_connection: doc.ssh_connection || '',
          docker_container: doc.docker_container || '',
          docker_context: doc.docker_context || '',
          docker_workdir: doc.docker_workdir || '',
          timeout_seconds: doc.timeout_seconds ?? 120,
          max_output_bytes: doc.max_output_bytes ?? 1048576,
          owner_user: doc.owner_user || '',
          tenancy_policy: doc.tenancy_policy || 'owner_only',
          allowed_users_json: doc.allowed_users_json || '',
          allowed_roles_json: doc.allowed_roles_json || '',
        });
      } catch (error) {
        toast.error('Failed to load Subscription Runtime', {
          description: getFrappeErrorMessage(error),
        });
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    loadRuntime();
    return () => {
      cancelled = true;
    };
  }, [id, isNew, form]);

  const onSubmit = async (values: SubscriptionRuntimeFormValues) => {
    setSaving(true);
    try {
      const payload: Partial<SubscriptionRuntimeDoc> = {
        runtime_name: values.runtime_name,
        enabled: values.enabled ? 1 : 0,
        provider_family: values.provider_family,
        cli_type: values.cli_type || undefined,
        cli_path: values.cli_path || undefined,
        transport_type: values.transport_type,
        working_directory: values.working_directory || undefined,
        timeout_seconds: values.timeout_seconds,
        max_output_bytes: values.max_output_bytes,
        owner_user: values.owner_user || undefined,
        tenancy_policy: values.tenancy_policy,
        allowed_users_json: values.allowed_users_json || undefined,
        allowed_roles_json: values.allowed_roles_json || undefined,
      };

      if (values.transport_type === 'SSH') {
        payload.ssh_connection = values.ssh_connection || undefined;
      }
      if (values.transport_type === 'Docker') {
        payload.docker_container = values.docker_container || undefined;
        payload.docker_context = values.docker_context || undefined;
        payload.docker_workdir = values.docker_workdir || undefined;
      }

      if (isNew) {
        const created = await createSubscriptionRuntime(payload);
        toast.success('Subscription Runtime created successfully');
        navigate(`/subscription-runtimes/${created.name || created.runtime_name}`);
      } else {
        const updated = await updateSubscriptionRuntime(id!, payload);
        toast.success('Subscription Runtime updated successfully');
        setRuntimeDoc(updated);
      }
    } catch (error) {
      toast.error(isNew ? 'Failed to create Subscription Runtime' : 'Failed to update Subscription Runtime', {
        description: getFrappeErrorMessage(error),
      });
    } finally {
      setSaving(false);
    }
  };

  const handleTestRuntime = async () => {
    if (isNew || !id) {
      toast.error('Save runtime first before testing');
      return;
    }

    setTesting(true);
    setTestResult(null);
    try {
      const res = await testSubscriptionRuntimeConnection(id);
      setTestResult(res);
      if (res.success) {
        toast.success('Runtime test succeeded!');
      } else {
        toast.error('Runtime test failed', { description: res.error });
      }
      const refreshed = await getSubscriptionRuntime(id);
      setRuntimeDoc(refreshed);
    } catch (error) {
      toast.error('Runtime test failed', { description: getFrappeErrorMessage(error) });
    } finally {
      setTesting(false);
    }
  };

  const handleReauthenticate = async () => {
    if (isNew || !id) return;

    setReauthenticating(true);
    setAuthChallenge(null);
    try {
      const challenge = await reauthenticateSubscriptionRuntime(id);
      setAuthChallenge(challenge);
      toast.success('Re-authentication started');
      const refreshed = await getSubscriptionRuntime(id);
      setRuntimeDoc(refreshed);
    } catch (error) {
      toast.error('Failed to start re-authentication', { description: getFrappeErrorMessage(error) });
    } finally {
      setReauthenticating(false);
    }
  };

  const handleLogout = async () => {
    if (isNew || !id) return;
    if (
      !confirm(
        'Are you sure you want to log out this runtime? Every conversation using it will lose access until it is re-authenticated.'
      )
    ) {
      return;
    }

    setLoggingOut(true);
    try {
      const res = await logoutSubscriptionRuntime(id);
      toast.success('Runtime logged out');
      setAuthChallenge(null);
      const refreshed = await getSubscriptionRuntime(id);
      setRuntimeDoc(refreshed);
      void res;
    } catch (error) {
      toast.error('Failed to log out runtime', { description: getFrappeErrorMessage(error) });
    } finally {
      setLoggingOut(false);
    }
  };

  const handleDelete = async () => {
    if (!id || isNew) return;
    if (!confirm('Are you sure you want to delete this Subscription Runtime?')) return;

    setDeleting(true);
    try {
      await deleteSubscriptionRuntime(id);
      toast.success('Subscription Runtime deleted');
      navigate('/subscription-runtimes');
    } catch (error) {
      toast.error('Failed to delete Subscription Runtime', {
        description: getFrappeErrorMessage(error),
      });
    } finally {
      setDeleting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-8 w-8 animate-spin text-steel-soft" />
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-4xl mx-auto pb-12">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-start gap-3">
          <Cpu className="h-8 w-8 text-steel-soft shrink-0 mt-1" strokeWidth={1.6} />
          <div>
            <InlineEditName
              value={form.watch('runtime_name') || (isNew ? 'New Subscription Runtime' : id!)}
              onChange={(name: string) => form.setValue('runtime_name', name, { shouldDirty: true })}
              placeholder="e.g. claude-primary"
              className="[&_h1]:font-display [&_h1]:text-[34px] [&_h1]:leading-tight"
              disabled={!isNew}
            />
            <p className="font-mono text-[12px] text-steel mt-1">
              {isNew ? 'Create a new subscription CLI runtime' : `ID ${id}`}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {!isNew && (
            <>
              <Button variant="outline" size="sm" onClick={handleTestRuntime} disabled={testing} className="border-line hover:border-ink hover:bg-paper-deep">
                {testing ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Play className="h-4 w-4 mr-2 text-steel" />}
                Test runtime
              </Button>
              <Button variant="outline" size="sm" onClick={handleReauthenticate} disabled={reauthenticating} className="border-line hover:border-ink hover:bg-paper-deep">
                {reauthenticating ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <RefreshCw className="h-4 w-4 mr-2 text-steel" />}
                Re-authenticate
              </Button>
              <Button variant="outline" size="sm" onClick={handleLogout} disabled={loggingOut} className="border-line hover:border-ink hover:bg-paper-deep">
                {loggingOut ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <LogOut className="h-4 w-4 mr-2 text-steel" />}
                Logout
              </Button>
              <Button variant="outline" size="sm" onClick={handleDelete} disabled={deleting || saving} className="border-line hover:border-ink hover:bg-paper-deep">
                {deleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4 text-destructive" />}
              </Button>
            </>
          )}
          <Button onClick={form.handleSubmit(onSubmit)} disabled={saving}>
            {saving ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Save className="h-4 w-4 mr-2" />}
            {isNew ? 'Create Runtime' : 'Save Changes'}
          </Button>
        </div>
      </div>

      {testResult && (
        <Card className="border-line bg-panel">
          <CardHeader>
            <CardTitle className="text-subtitle">Test result</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-2 sm:grid-cols-2 text-sm">
            <div>
              <span className="font-mono text-[10px] uppercase tracking-wide text-steel-soft block">Success</span>
              <span className="font-body text-[13px] text-ink">{testResult.success ? 'Yes' : 'No'}</span>
            </div>
            <div>
              <span className="font-mono text-[10px] uppercase tracking-wide text-steel-soft block">Version</span>
              <span className="font-mono text-[12px] text-ink">{testResult.version || 'Unknown'}</span>
            </div>
            <div>
              <span className="font-mono text-[10px] uppercase tracking-wide text-steel-soft block">Authenticated</span>
              <span className="font-body text-[13px] text-ink">{testResult.authenticated ? 'Yes' : 'No'}</span>
            </div>
            {testResult.error && (
              <div className="sm:col-span-2">
                <span className="font-mono text-[10px] uppercase tracking-wide text-steel-soft block">Error</span>
                <span className="font-mono text-[12px] text-destructive break-words">{testResult.error}</span>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {authChallenge && (
        <Card className="border-line bg-panel">
          <CardHeader>
            <CardTitle className="text-subtitle">Authentication challenge</CardTitle>
            <CardDescription className="font-body text-ui-text text-steel">
              Follow the instructions below to finish signing in. This runtime will move to "Ready" once the
              CLI session confirms.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2 text-sm">
            <div>
              <span className="font-mono text-[10px] uppercase tracking-wide text-steel-soft block">Status</span>
              <span className="font-body text-[13px] text-ink">{authChallenge.status}</span>
            </div>
            {authChallenge.mode && (
              <div>
                <span className="font-mono text-[10px] uppercase tracking-wide text-steel-soft block">Mode</span>
                <span className="font-mono text-[12px] text-ink">{authChallenge.mode}</span>
              </div>
            )}
            {authChallenge.verification_url && (
              <div>
                <span className="font-mono text-[10px] uppercase tracking-wide text-steel-soft block">Verification URL</span>
                <a
                  href={authChallenge.verification_url}
                  target="_blank"
                  rel="noreferrer"
                  className="font-mono text-[12px] text-ink underline break-all"
                >
                  {authChallenge.verification_url}
                </a>
              </div>
            )}
            {authChallenge.user_code && (
              <div>
                <span className="font-mono text-[10px] uppercase tracking-wide text-steel-soft block">Code</span>
                <span className="font-mono text-[13px] text-ink">{authChallenge.user_code}</span>
              </div>
            )}
            {authChallenge.safe_instructions && (
              <div className="sm:col-span-2">
                <span className="font-mono text-[10px] uppercase tracking-wide text-steel-soft block">Instructions</span>
                <span className="font-body text-[13px] text-ink whitespace-pre-wrap">{authChallenge.safe_instructions}</span>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
          <Card className="border-line bg-panel">
            <CardHeader>
              <CardTitle className="text-subtitle">Identity</CardTitle>
              <CardDescription className="font-body text-ui-text text-steel">
                What this runtime is and which provider family it belongs to
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <FormField
                control={form.control}
                name="runtime_name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Runtime name</FormLabel>
                    <FormControl>
                      <Input placeholder="e.g. claude-primary" {...field} disabled={!isNew} />
                    </FormControl>
                    <FormDescription>Unique identifier. Cannot be changed after creation.</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="enabled"
                render={({ field }) => (
                  <FormItem className="flex flex-row items-center justify-between border border-line bg-paper p-4">
                    <div className="space-y-0.5">
                      <FormLabel className="text-base">Enable runtime</FormLabel>
                      <FormDescription>Disabled runtimes cannot be used by agents.</FormDescription>
                    </div>
                    <FormControl>
                      <Switch checked={field.value} onCheckedChange={field.onChange} />
                    </FormControl>
                  </FormItem>
                )}
              />

              <div className="grid gap-6 sm:grid-cols-3">
                <FormField
                  control={form.control}
                  name="provider_family"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Provider family</FormLabel>
                      <Select onValueChange={field.onChange} value={field.value}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="Select provider" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value="Claude">Claude</SelectItem>
                          <SelectItem value="Codex">Codex</SelectItem>
                          <SelectItem value="Gemini">Gemini</SelectItem>
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="cli_type"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>CLI type</FormLabel>
                      <FormControl>
                        <Input placeholder="claude / codex / gemini" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="cli_path"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>CLI path</FormLabel>
                      <FormControl>
                        <Input placeholder="/usr/local/bin/claude" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
            </CardContent>
          </Card>

          <Card className="border-line bg-panel">
            <CardHeader>
              <CardTitle className="text-subtitle">Transport</CardTitle>
              <CardDescription className="font-body text-ui-text text-steel">
                Where the CLI process actually runs
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <FormField
                control={form.control}
                name="transport_type"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Transport type</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select transport" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="Local">Local</SelectItem>
                        <SelectItem value="Docker">Docker</SelectItem>
                        <SelectItem value="SSH">SSH</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {watchTransportType !== 'Local' && (
                <FormField
                  control={form.control}
                  name="working_directory"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Working directory</FormLabel>
                      <FormControl>
                        <Input placeholder="/workspace" {...field} />
                      </FormControl>
                      <FormDescription>Required for non-Local transports.</FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              )}

              {watchTransportType === 'SSH' && (
                <FormField
                  control={form.control}
                  name="ssh_connection"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>SSH connection</FormLabel>
                      <Select onValueChange={field.onChange} value={field.value}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="Select an SSH connection" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {sshConnections.map((conn) => (
                            <SelectItem key={conn.name} value={conn.name}>
                              {conn.display_name || conn.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FormDescription>
                        Manage credentials for this connection under SSH connections.
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              )}

              {watchTransportType === 'Docker' && (
                <div className="grid gap-6 sm:grid-cols-3">
                  <FormField
                    control={form.control}
                    name="docker_container"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Docker container</FormLabel>
                        <FormControl>
                          <Input placeholder="container name or id" {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="docker_context"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Docker context</FormLabel>
                        <FormControl>
                          <Input placeholder="default" {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="docker_workdir"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Docker workdir</FormLabel>
                        <FormControl>
                          <Input placeholder="/app" {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>
              )}
            </CardContent>
          </Card>

          <Card className="border-line bg-panel">
            <CardHeader>
              <CardTitle className="text-subtitle">Limits</CardTitle>
              <CardDescription className="font-body text-ui-text text-steel">
                Guardrails applied to every command run through this runtime
              </CardDescription>
            </CardHeader>
            <CardContent className="grid gap-6 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="timeout_seconds"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Timeout (seconds)</FormLabel>
                    <FormControl>
                      <Input type="number" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="max_output_bytes"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Max output bytes</FormLabel>
                    <FormControl>
                      <Input type="number" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </CardContent>
          </Card>

          <Card className="border-line bg-panel">
            <CardHeader>
              <CardTitle className="text-subtitle">Tenancy</CardTitle>
              <CardDescription className="font-body text-ui-text text-steel">
                Who is allowed to use this runtime
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="grid gap-6 sm:grid-cols-2">
                <FormField
                  control={form.control}
                  name="owner_user"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Owner user</FormLabel>
                      <FormControl>
                        <Input placeholder="user@example.com" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="tenancy_policy"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Tenancy policy</FormLabel>
                      <Select onValueChange={field.onChange} value={field.value}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="Select policy" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value="owner_only">Owner only</SelectItem>
                          <SelectItem value="explicit_users">Explicit users</SelectItem>
                          <SelectItem value="explicit_roles">Explicit roles</SelectItem>
                          <SelectItem value="system_managed_shared">System managed (shared)</SelectItem>
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              {watchTenancyPolicy === 'explicit_users' && (
                <FormField
                  control={form.control}
                  name="allowed_users_json"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Allowed users (JSON)</FormLabel>
                      <FormControl>
                        <Textarea
                          placeholder='["user1@example.com", "user2@example.com"]'
                          className="font-mono text-xs min-h-[100px]"
                          {...field}
                        />
                      </FormControl>
                      <FormDescription>JSON array of allowed user emails.</FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              )}

              {watchTenancyPolicy === 'explicit_roles' && (
                <FormField
                  control={form.control}
                  name="allowed_roles_json"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Allowed roles (JSON)</FormLabel>
                      <FormControl>
                        <Textarea
                          placeholder='["Huf Manager", "System Manager"]'
                          className="font-mono text-xs min-h-[100px]"
                          {...field}
                        />
                      </FormControl>
                      <FormDescription>JSON array of allowed role names.</FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              )}
            </CardContent>
          </Card>

          {!isNew && runtimeDoc && (
            <Card className="border-line bg-panel">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-subtitle">
                  <ShieldCheck className="h-5 w-5 text-steel-soft" strokeWidth={1.6} />
                  Status
                </CardTitle>
                <CardDescription className="font-body text-ui-text text-steel">
                  Read-only state captured by the last probe and authentication check
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid gap-4 sm:grid-cols-2 border border-line bg-paper p-4 text-sm">
                  <div>
                    <span className="font-mono text-[10px] uppercase tracking-wide text-steel-soft block">Detected Version</span>
                    <span className="font-mono text-[12px] text-ink break-all">
                      {runtimeDoc.detected_version || 'Not detected yet'}
                    </span>
                  </div>

                  <div>
                    <span className="font-mono text-[10px] uppercase tracking-wide text-steel-soft block">Last Tested On</span>
                    <span className="font-mono text-[12px] text-ink">
                      {runtimeDoc.last_tested_on || 'Never'}
                    </span>
                  </div>

                  <div>
                    <span className="font-mono text-[10px] uppercase tracking-wide text-steel-soft block">Last Test Status</span>
                    <div className="mt-1 flex items-center gap-2">
                      {runtimeDoc.last_test_status === 'Success' ? (
                        <>
                          <StatusDot variant="ok" />
                          <span className="font-body text-[13px] text-steel">Success</span>
                        </>
                      ) : runtimeDoc.last_test_status ? (
                        <>
                          <StatusDot variant="fail" />
                          <span className="font-body text-[13px] text-steel">{runtimeDoc.last_test_status}</span>
                        </>
                      ) : (
                        <>
                          <StatusDot variant="idle" />
                          <span className="font-body text-[13px] text-steel">Not tested</span>
                        </>
                      )}
                    </div>
                  </div>

                  <div>
                    <span className="font-mono text-[10px] uppercase tracking-wide text-steel-soft block">Last Error</span>
                    <span className="font-mono text-[12px] text-destructive break-words">
                      {runtimeDoc.last_error || 'None'}
                    </span>
                  </div>

                  <div>
                    <span className="font-mono text-[10px] uppercase tracking-wide text-steel-soft block">Auth Status</span>
                    <span className="font-body text-[13px] text-ink">
                      {AUTH_STATUS_LABELS[runtimeDoc.auth_status || 'unknown'] || runtimeDoc.auth_status}
                    </span>
                  </div>

                  <div>
                    <span className="font-mono text-[10px] uppercase tracking-wide text-steel-soft block">Auth Method</span>
                    <span className="font-mono text-[12px] text-ink">{runtimeDoc.auth_method || 'N/A'}</span>
                  </div>

                  <div>
                    <span className="font-mono text-[10px] uppercase tracking-wide text-steel-soft block">Account Hint</span>
                    <span className="font-mono text-[12px] text-ink">{runtimeDoc.auth_account_hint || 'N/A'}</span>
                  </div>

                  <div>
                    <span className="font-mono text-[10px] uppercase tracking-wide text-steel-soft block">Last Auth Checked</span>
                    <span className="font-mono text-[12px] text-ink">{runtimeDoc.last_auth_checked_at || 'Never'}</span>
                  </div>

                  <div>
                    <span className="font-mono text-[10px] uppercase tracking-wide text-steel-soft block">Last Auth Success</span>
                    <span className="font-mono text-[12px] text-ink">{runtimeDoc.last_auth_success_at || 'Never'}</span>
                  </div>

                  <div>
                    <span className="font-mono text-[10px] uppercase tracking-wide text-steel-soft block">Last Auth Failure</span>
                    <span className="font-mono text-[12px] text-ink">{runtimeDoc.last_auth_failure_at || 'Never'}</span>
                  </div>

                  <div>
                    <span className="font-mono text-[10px] uppercase tracking-wide text-steel-soft block">Auth Error Code</span>
                    <span className="font-mono text-[12px] text-ink">{runtimeDoc.auth_error_code || 'None'}</span>
                  </div>

                  <div>
                    <span className="font-mono text-[10px] uppercase tracking-wide text-steel-soft block">Auth Error Message</span>
                    <span className="font-mono text-[12px] text-destructive break-words">
                      {runtimeDoc.auth_error_message || 'None'}
                    </span>
                  </div>

                  {runtimeDoc.capabilities_snapshot && (
                    <div className="sm:col-span-2">
                      <span className="font-mono text-[10px] uppercase tracking-wide text-steel-soft block">Capabilities</span>
                      <pre className="font-mono text-[11px] text-ink whitespace-pre-wrap break-all mt-1">
                        {runtimeDoc.capabilities_snapshot}
                      </pre>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          )}
        </form>
      </Form>
    </div>
  );
}

export default SubscriptionRuntimeFormPage;
