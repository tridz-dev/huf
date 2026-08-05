import { useEffect, useState } from 'react';
import { useNavigate, useParams, useLocation } from 'react-router-dom';
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
import { Save, Trash2, Terminal, Loader2, Play, ShieldCheck, RefreshCw } from 'lucide-react';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import {
  createSSHConnection,
  deleteSSHConnection,
  enrollHostKey,
  getSSHConnection,
  testSSHConnection,
  updateSSHConnection,
  type SSHConnectionDoc,
  type SSHTestResult,
} from '@/services/sshConnectionApi';
import { InlineEditName } from '@/components/common/InlineEditName';

const sshConnectionSchema = z.object({
  display_name: z.string().min(1, 'Display name is required'),
  enabled: z.boolean().default(true),
  host: z.string().min(1, 'Host address is required'),
  port: z.coerce.number().min(1, 'Port must be positive').default(22),
  username: z.string().min(1, 'Username is required'),
  auth_method: z.enum(['Password', 'Private Key']).default('Password'),
  password: z.string().optional(),
  private_key: z.string().optional(),
  private_key_passphrase: z.string().optional(),
  host_key_verification: z.enum(['Strict (Pinned)']).default('Strict (Pinned)'),
});

type SSHConnectionFormValues = z.infer<typeof sshConnectionSchema>;

export function SSHConnectionFormPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const isNew = id === 'new';
  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [testing, setTesting] = useState(false);
  const [enrolling, setEnrolling] = useState(false);
  const [, setTestResult] = useState<SSHTestResult | null>(null);
  const [connectionDoc, setConnectionDoc] = useState<SSHConnectionDoc | null>(null);

  const form = useForm<SSHConnectionFormValues>({
    resolver: zodResolver(sshConnectionSchema),
    defaultValues: {
      display_name: '',
      enabled: true,
      host: '',
      port: 22,
      username: '',
      auth_method: 'Password',
      password: '',
      private_key: '',
      private_key_passphrase: '',
      host_key_verification: 'Strict (Pinned)',
    },
  });

  const watchAuthMethod = form.watch('auth_method');

  useEffect(() => {
    if (isNew) {
      setLoading(false);
      return;
    }

    let cancelled = false;
    const loadConnection = async () => {
      try {
        const conn = await getSSHConnection(id!);
        if (cancelled) return;

        setConnectionDoc(conn);
        form.reset({
          display_name: conn.display_name || conn.name,
          enabled: conn.enabled === 1,
          host: conn.host || '',
          port: conn.port ?? 22,
          username: conn.username || '',
          auth_method: conn.auth_method || 'Password',
          password: '', // Blank for security unless updated
          private_key: '',
          private_key_passphrase: '',
          host_key_verification: 'Strict (Pinned)',
        });
      } catch (error) {
        toast.error('Failed to load SSH Connection', {
          description: getFrappeErrorMessage(error),
        });
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    loadConnection();
    return () => {
      cancelled = true;
    };
  }, [id, isNew, form]);

  const handleReturnNavigation = (createdName: string) => {
    let returnTo: string | null = null;

    const state = location.state as { returnTo?: string } | null;
    if (state?.returnTo) {
      returnTo = state.returnTo;
    } else {
      try {
        const stored = localStorage.getItem('sshConnectionCreateReturnTo');
        if (stored) {
          const parsed = JSON.parse(stored);
          returnTo = parsed.returnTo;
          localStorage.removeItem('sshConnectionCreateReturnTo');
        }
      } catch {
        // ignore storage errors
      }
    }

    if (returnTo) {
      navigate(returnTo, {
        state: {
          selectedSSHConnection: createdName,
          showTab: 'advanced',
        },
        replace: true,
      });
    } else {
      navigate(`/ssh-connections/${createdName}`);
    }
  };

  const onSubmit = async (values: SSHConnectionFormValues) => {
    setSaving(true);
    try {
      const payload: Partial<SSHConnectionDoc> = {
        display_name: values.display_name,
        enabled: values.enabled ? 1 : 0,
        host: values.host,
        port: values.port,
        username: values.username,
        auth_method: values.auth_method,
        host_key_verification: values.host_key_verification,
      };

      if (values.auth_method === 'Password' && values.password) {
        payload.password = values.password;
      }
      if (values.auth_method === 'Private Key') {
        if (values.private_key) payload.private_key = values.private_key;
        if (values.private_key_passphrase) payload.private_key_passphrase = values.private_key_passphrase;
      }

      if (isNew) {
        const created = await createSSHConnection(payload);
        toast.success('SSH Connection created successfully');
        handleReturnNavigation(created.name || created.display_name);
      } else {
        const updated = await updateSSHConnection(id!, payload);
        toast.success('SSH Connection updated successfully');
        setConnectionDoc(updated);
      }
    } catch (error) {
      toast.error(isNew ? 'Failed to create SSH Connection' : 'Failed to update SSH Connection', {
        description: getFrappeErrorMessage(error),
      });
    } finally {
      setSaving(false);
    }
  };

  const handleTestConnection = async () => {
    if (isNew || !id) {
      toast.error('Save connection first before testing');
      return;
    }

    setTesting(true);
    setTestResult(null);
    try {
      const res = await testSSHConnection(id);
      setTestResult(res);
      if (res.success) {
        toast.success('SSH Connection test succeeded!');
      } else {
        toast.error('SSH Connection test failed', { description: res.error });
      }
      // Refresh doc metadata
      const refreshed = await getSSHConnection(id);
      setConnectionDoc(refreshed);
    } catch (error) {
      toast.error('SSH Connection test failed', { description: getFrappeErrorMessage(error) });
    } finally {
      setTesting(false);
    }
  };

  const handleEnrollHostKey = async () => {
    if (isNew || !id) return;

    setEnrolling(true);
    try {
      const res = await enrollHostKey(id);
      if (res.success) {
        toast.success('Host key enrolled successfully!');
        const refreshed = await getSSHConnection(id);
        setConnectionDoc(refreshed);
      } else {
        toast.error('Failed to enroll host key', { description: res.error });
      }
    } catch (error) {
      toast.error('Failed to enroll host key', { description: getFrappeErrorMessage(error) });
    } finally {
      setEnrolling(false);
    }
  };

  const handleDelete = async () => {
    if (!id || isNew) return;
    if (!confirm('Are you sure you want to delete this SSH Connection?')) return;

    setDeleting(true);
    try {
      await deleteSSHConnection(id);
      toast.success('SSH Connection deleted');
      navigate('/ssh-connections');
    } catch (error) {
      toast.error('Failed to delete SSH Connection', {
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
          <Terminal className="h-8 w-8 text-steel-soft shrink-0 mt-1" strokeWidth={1.6} />
          <div>
            <InlineEditName
              value={form.watch('display_name') || (isNew ? 'New SSH Connection' : id!)}
              onChange={(name: string) => form.setValue('display_name', name, { shouldDirty: true })}
              placeholder="e.g. Production Web Server"
              className="[&_h1]:font-display [&_h1]:text-[34px] [&_h1]:leading-tight"
            />
            <p className="font-mono text-[12px] text-steel mt-1">
              {isNew ? 'Create a new remote SSH target connection' : `ID ${id}`}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {!isNew && (
            <>
              <Button variant="outline" size="sm" onClick={handleTestConnection} disabled={testing} className="border-line hover:border-ink hover:bg-paper-deep">
                {testing ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Play className="h-4 w-4 mr-2 text-steel" />}
                Test connection
              </Button>
              <Button variant="outline" size="sm" onClick={handleDelete} disabled={deleting || saving} className="border-line hover:border-ink hover:bg-paper-deep">
                {deleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4 text-destructive" />}
              </Button>
            </>
          )}
          <Button onClick={form.handleSubmit(onSubmit)} disabled={saving}>
            {saving ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Save className="h-4 w-4 mr-2" />}
            {isNew ? 'Create Connection' : 'Save Changes'}
          </Button>
        </div>
      </div>

      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
          <Card className="border-line bg-panel">
            <CardHeader>
              <CardTitle className="text-subtitle">Connection Details</CardTitle>
              <CardDescription className="font-body text-[13px] text-steel">Specify target hostname, port, and authentication credentials</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <FormField
                control={form.control}
                name="display_name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Display Name</FormLabel>
                    <FormControl>
                      <Input placeholder="e.g. Production Web Worker 01" {...field} />
                    </FormControl>
                    <FormDescription>Friendly identifier for selecting this connection in agents.</FormDescription>
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
                      <FormLabel className="text-base">Enable Connection</FormLabel>
                      <FormDescription>Disabled connections cannot be executed against by AI agents.</FormDescription>
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
                  name="host"
                  render={({ field }) => (
                    <FormItem className="sm:col-span-2">
                      <FormLabel>Host / IP Address</FormLabel>
                      <FormControl>
                        <Input placeholder="192.168.1.10 or server.example.com" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="port"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Port</FormLabel>
                      <FormControl>
                        <Input type="number" placeholder="22" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              <FormField
                control={form.control}
                name="username"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>SSH Username</FormLabel>
                    <FormControl>
                      <Input placeholder="root or ubuntu or deploy" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="auth_method"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Authentication Method</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select auth method" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="Password">Password</SelectItem>
                        <SelectItem value="Private Key">Private Key</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {watchAuthMethod === 'Password' && (
                <FormField
                  control={form.control}
                  name="password"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Password</FormLabel>
                      <FormControl>
                        <Input
                          type="password"
                          placeholder={isNew ? 'Enter SSH password' : '•••••••• (leave blank to keep existing)'}
                          {...field}
                        />
                      </FormControl>
                      <FormDescription>Stored securely using Frappe encrypted password fields.</FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              )}

              {watchAuthMethod === 'Private Key' && (
                <>
                  <FormField
                    control={form.control}
                    name="private_key"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Private Key (PEM format)</FormLabel>
                        <FormControl>
                          <Textarea
                            placeholder={isNew ? '-----BEGIN OPENSSH PRIVATE KEY-----...' : 'Leave blank to keep existing private key'}
                            className="font-mono text-xs min-h-[120px]"
                            {...field}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="private_key_passphrase"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Passphrase (Optional)</FormLabel>
                        <FormControl>
                          <Input
                            type="password"
                            placeholder="Passphrase for encrypted private key"
                            {...field}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </>
              )}
            </CardContent>
          </Card>

          {!isNew && connectionDoc && (
            <Card className="border-line bg-panel">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-subtitle">
                  <ShieldCheck className="h-5 w-5 text-steel-soft" strokeWidth={1.6} />
                  Host Key Security & Status
                </CardTitle>
                <CardDescription className="font-body text-[13px] text-steel">Pinned host key verification prevents MITM attacks</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid gap-4 sm:grid-cols-2 border border-line bg-paper p-4 text-sm">
                  <div>
                    <span className="font-mono text-[10px] uppercase tracking-wide text-steel-soft block">Host Key Fingerprint</span>
                    <span className="font-mono text-[12px] text-ink break-all">
                      {connectionDoc.host_key_fingerprint || 'Not enrolled yet'}
                    </span>
                  </div>

                  <div>
                    <span className="font-mono text-[10px] uppercase tracking-wide text-steel-soft block">Host Key Type</span>
                    <span className="font-mono text-[12px] text-ink">
                      {connectionDoc.host_key_type || 'N/A'}
                    </span>
                  </div>

                  <div>
                    <span className="font-mono text-[10px] uppercase tracking-wide text-steel-soft block">Last Test Status</span>
                    <div className="mt-1 flex items-center gap-2">
                      {connectionDoc.last_test_status === 'Success' ? (
                        <>
                          <StatusDot variant="ok" />
                          <span className="font-body text-[13px] text-steel">Success</span>
                        </>
                      ) : connectionDoc.last_test_status ? (
                        <>
                          <StatusDot variant="fail" />
                          <span className="font-body text-[13px] text-steel">Failed</span>
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
                      {connectionDoc.last_error || 'None'}
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-3 pt-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={handleEnrollHostKey}
                    disabled={enrolling}
                    className="border-line hover:border-ink hover:bg-paper-deep"
                  >
                    {enrolling ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <RefreshCw className="h-4 w-4 mr-2" />}
                    Enroll / Update Host Key
                  </Button>
                  <span className="font-body text-xs text-steel">
                    Connects to target server to automatically fetch and pin its public host key fingerprint.
                  </span>
                </div>
              </CardContent>
            </Card>
          )}
        </form>
      </Form>
    </div>
  );
}

export default SSHConnectionFormPage;
