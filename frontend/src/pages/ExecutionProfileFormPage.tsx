import { useEffect, useState } from 'react';
import { useNavigate, useParams, useLocation, Link } from 'react-router-dom';
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
import { Save, Trash2, ShieldCheck, Loader2, Plus } from 'lucide-react';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import {
  createExecutionProfile,
  deleteExecutionProfile,
  getExecutionProfile,
  updateExecutionProfile,
  type ExecutionProfileDoc,
} from '@/services/executionProfileApi';
import { getNetworkAccessPolicies, type NetworkAccessPolicyDoc } from '@/services/networkAccessPolicyApi';
import { getDocTypes } from '@/services/agentApi';
import type { ComboboxOption } from '@/components/ui/combobox';
import { InlineEditName } from '@/components/common/InlineEditName';
import {
  ExecutionProfilePermissionCard,
  type ExecutionProfilePermissionFormRow,
} from '@/components/execution-profile/ExecutionProfilePermissionCard';

const executionProfilePermissionSchema = z.object({
  name: z.string().optional(),
  capability: z.string(),
  reference_doctype: z.string().optional(),
  is_read_only: z.boolean().optional(),
});

const executionProfileSchema = z.object({
  profile_name: z.string().min(1, 'Profile name is required'),
  disabled: z.boolean().default(false),
  approval_mode: z.enum(['Auto Approve', 'Ask Every Time', 'Never Allow']).default('Ask Every Time'),
  filesystem_policy: z.enum(['None', 'Scratch Only', 'Shared Directory']).default('None'),
  network_policy: z.string().optional(),
  allowed_modules: z.string().optional(),
  max_wall_time_s: z.coerce.number().min(1, 'Wall time limit must be at least 1s').default(30),
  max_cpu_seconds: z.coerce.number().min(1, 'CPU limit must be at least 1s').default(30),
  max_memory_mb: z.coerce.number().min(1, 'Memory limit must be at least 1MB').default(256),
  max_output_bytes: z.coerce.number().min(1024, 'Output limit must be at least 1024 bytes').default(1048576),
  permissions: z.array(executionProfilePermissionSchema).default([]),
});

type ExecutionProfileFormValues = z.infer<typeof executionProfileSchema>;

export function ExecutionProfileFormPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const isNew = id === 'new';
  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [, setProfileDoc] = useState<ExecutionProfileDoc | null>(null);
  const [networkPolicies, setNetworkPolicies] = useState<NetworkAccessPolicyDoc[]>([]);
  const [loadingNetworkPolicies, setLoadingNetworkPolicies] = useState(true);
  const [docTypeOptions, setDocTypeOptions] = useState<ComboboxOption[]>([]);
  const [loadingDocTypes, setLoadingDocTypes] = useState(true);

  const form = useForm<ExecutionProfileFormValues>({
    resolver: zodResolver(executionProfileSchema),
    defaultValues: {
      profile_name: '',
      disabled: false,
      approval_mode: 'Ask Every Time',
      filesystem_policy: 'None',
      network_policy: '',
      allowed_modules: '["math", "json", "re", "datetime", "random", "typing"]',
      max_wall_time_s: 30,
      max_cpu_seconds: 30,
      max_memory_mb: 256,
      max_output_bytes: 1048576,
      permissions: [],
    },
  });

  useEffect(() => {
    let cancelled = false;
    const loadNetworkPolicies = async () => {
      try {
        const response = await getNetworkAccessPolicies({ limit: 100 });
        if (!cancelled) {
          setNetworkPolicies(response?.items || []);
        }
      } catch (error) {
        toast.error('Failed to load network access policies', {
          description: getFrappeErrorMessage(error),
        });
      } finally {
        if (!cancelled) {
          setLoadingNetworkPolicies(false);
        }
      }
    };

    loadNetworkPolicies();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const loadDocTypes = async () => {
      try {
        const docTypes = await getDocTypes();
        if (!cancelled) {
          setDocTypeOptions((docTypes || []).map((dt) => ({ value: dt.name, label: dt.name })));
        }
      } catch (error) {
        toast.error('Failed to load doctypes', {
          description: getFrappeErrorMessage(error),
        });
      } finally {
        if (!cancelled) {
          setLoadingDocTypes(false);
        }
      }
    };

    loadDocTypes();
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
    const loadProfile = async () => {
      try {
        const profile = await getExecutionProfile(id!);
        if (cancelled) return;

        setProfileDoc(profile);
        form.reset({
          profile_name: profile.profile_name || profile.name,
          disabled: profile.disabled === 1,
          approval_mode: profile.approval_mode || 'Ask Every Time',
          filesystem_policy: profile.filesystem_policy || 'None',
          network_policy: profile.network_policy || '',
          allowed_modules: profile.allowed_modules || '[]',
          max_wall_time_s: profile.max_wall_time_s ?? 30,
          max_cpu_seconds: profile.max_cpu_seconds ?? 30,
          max_memory_mb: profile.max_memory_mb ?? 256,
          max_output_bytes: profile.max_output_bytes ?? 1048576,
          permissions: (profile.permissions || []).map((permission) => ({
            name: permission.name,
            capability: permission.capability || '',
            reference_doctype: permission.reference_doctype || '',
            is_read_only: permission.is_read_only === 1,
          })),
        });
      } catch (error) {
        toast.error('Failed to load execution profile', {
          description: getFrappeErrorMessage(error),
        });
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    loadProfile();
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
        const stored = localStorage.getItem('executionProfileCreateReturnTo');
        if (stored) {
          const parsed = JSON.parse(stored);
          returnTo = parsed.returnTo;
          localStorage.removeItem('executionProfileCreateReturnTo');
        }
      } catch {
        // ignore storage errors
      }
    }

    if (returnTo) {
      navigate(returnTo, {
        state: {
          selectedExecutionProfile: createdName,
          showTab: 'advanced',
        },
        replace: true,
      });
    } else {
      navigate(`/execution-profiles/${createdName}`);
    }
  };

  const handleAddPermission = () => {
    const current = form.getValues('permissions') || [];
    form.setValue('permissions', [...current, { capability: '', reference_doctype: '', is_read_only: false }], {
      shouldDirty: true,
    });
  };

  const handleUpdatePermission = (index: number, data: Partial<ExecutionProfilePermissionFormRow>) => {
    const current = form.getValues('permissions') || [];
    const updated = [...current];
    updated[index] = { ...updated[index], ...data };
    form.setValue('permissions', updated, { shouldDirty: true });
  };

  const handleDeletePermission = (index: number) => {
    const current = form.getValues('permissions') || [];
    form.setValue(
      'permissions',
      current.filter((_, i) => i !== index),
      { shouldDirty: true }
    );
  };

  const onSubmit = async (values: ExecutionProfileFormValues) => {
    setSaving(true);
    try {
      const payload: Partial<ExecutionProfileDoc> = {
        profile_name: values.profile_name,
        disabled: values.disabled ? 1 : 0,
        approval_mode: values.approval_mode,
        filesystem_policy: values.filesystem_policy,
        network_policy: values.network_policy || undefined,
        allowed_modules: values.allowed_modules,
        max_wall_time_s: values.max_wall_time_s,
        max_cpu_seconds: values.max_cpu_seconds,
        max_memory_mb: values.max_memory_mb,
        max_output_bytes: values.max_output_bytes,
        permissions: (values.permissions || [])
          .filter((permission) => permission.capability?.trim())
          .map((permission) => ({
            name: permission.name,
            capability: permission.capability,
            reference_doctype: permission.reference_doctype || undefined,
            is_read_only: permission.is_read_only ? 1 : 0,
          })),
      };

      if (isNew) {
        const created = await createExecutionProfile(payload);
        toast.success('Execution profile created successfully');
        handleReturnNavigation(created.name || created.profile_name);
      } else {
        const updated = await updateExecutionProfile(id!, payload);
        toast.success('Execution profile updated successfully');
        setProfileDoc(updated);
      }
    } catch (error) {
      toast.error(isNew ? 'Failed to create execution profile' : 'Failed to update execution profile', {
        description: getFrappeErrorMessage(error),
      });
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!id || isNew) return;
    if (!confirm('Are you sure you want to delete this execution profile?')) return;

    setDeleting(true);
    try {
      await deleteExecutionProfile(id);
      toast.success('Execution profile deleted');
      navigate('/execution-profiles');
    } catch (error) {
      toast.error('Failed to delete execution profile', {
        description: getFrappeErrorMessage(error),
      });
    } finally {
      setDeleting(false);
    }
  };

  const permissions = form.watch('permissions') || [];

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-8 w-8 animate-spin text-steel-soft" />
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="space-y-6 max-w-4xl mx-auto p-6 pb-12">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-start gap-3">
          <ShieldCheck className="h-8 w-8 text-steel-soft shrink-0 mt-1" strokeWidth={1.6} />
          <div>
            <InlineEditName
              value={form.watch('profile_name') || (isNew ? 'New execution profile' : id!)}
              onChange={(name: string) => form.setValue('profile_name', name, { shouldDirty: true })}
              placeholder="e.g. Sandbox with network access"
              className="[&_h1]:font-display [&_h1]:text-[34px] [&_h1]:leading-tight"
            />
            <p className="font-mono text-[12px] text-steel mt-1">
              {isNew ? 'Create a new sandboxed execution profile' : `ID ${id}`}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {!isNew && (
            <Button variant="outline" size="sm" onClick={handleDelete} disabled={deleting || saving} className="border-line hover:border-ink hover:bg-paper-deep">
              {deleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4 text-destructive" />}
            </Button>
          )}
          <Button onClick={form.handleSubmit(onSubmit)} disabled={saving}>
            {saving ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Save className="h-4 w-4 mr-2" />}
            {isNew ? 'Create Profile' : 'Save Changes'}
          </Button>
        </div>
      </div>

      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
          <Card className="border-line bg-panel">
            <CardHeader>
              <CardTitle className="text-subtitle">General settings</CardTitle>
              <CardDescription className="font-body text-ui-text text-steel">Configure security policy and sandbox behavior</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <FormField
                control={form.control}
                name="profile_name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Profile name</FormLabel>
                    <FormControl>
                      <Input placeholder="e.g. Standard Sandbox" {...field} />
                    </FormControl>
                    <FormDescription>Unique name identifying this execution environment.</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="disabled"
                render={({ field }) => (
                  <FormItem className="flex flex-row items-center justify-between border border-line bg-paper p-4">
                    <div className="space-y-0.5">
                      <FormLabel className="text-base">Disable profile</FormLabel>
                      <FormDescription>Disabled profiles cannot be selected or used for code execution.</FormDescription>
                    </div>
                    <FormControl>
                      <Switch checked={field.value} onCheckedChange={field.onChange} />
                    </FormControl>
                  </FormItem>
                )}
              />

              <div className="grid gap-6 sm:grid-cols-2">
                <FormField
                  control={form.control}
                  name="approval_mode"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Approval mode</FormLabel>
                      <Select onValueChange={field.onChange} value={field.value}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="Select approval mode" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value="Auto Approve">Auto Approve</SelectItem>
                          <SelectItem value="Ask Every Time">Ask Every Time</SelectItem>
                          <SelectItem value="Never Allow">Never Allow</SelectItem>
                        </SelectContent>
                      </Select>
                      <FormDescription>Determines whether user confirmation is required before code executes.</FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="filesystem_policy"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Filesystem policy</FormLabel>
                      <Select onValueChange={field.onChange} value={field.value}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="Select filesystem policy" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value="None">None</SelectItem>
                          <SelectItem value="Scratch Only">Scratch Only</SelectItem>
                          <SelectItem value="Shared Directory">Shared Directory</SelectItem>
                        </SelectContent>
                      </Select>
                      <FormDescription>Controls local disk read/write privileges for the execution sandbox.</FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              <FormField
                control={form.control}
                name="network_policy"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Network access policy</FormLabel>
                    {networkPolicies.length === 0 && !loadingNetworkPolicies ? (
                      <div className="flex items-center justify-between gap-4 border border-line bg-paper p-4 text-sm">
                        <span className="text-steel">No network access policies exist yet. Create one to control outbound network access for this profile.</span>
                        <Button type="button" variant="outline" size="sm" asChild className="shrink-0 border-line hover:border-ink hover:bg-paper-deep">
                          <Link to="/network-policies">Create policy</Link>
                        </Button>
                      </div>
                    ) : (
                      <Select onValueChange={field.onChange} value={field.value || ''} disabled={loadingNetworkPolicies}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder={loadingNetworkPolicies ? 'Loading policies...' : 'No network policy (unrestricted egress)'} />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {networkPolicies.map((policy) => (
                            <SelectItem key={policy.name} value={policy.name}>
                              {policy.policy_name || policy.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    )}
                    <FormDescription>Restricts outbound network requests made by the sandbox to the hosts allowed by this policy. Leave unset to allow unrestricted egress.</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="allowed_modules"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Allowed python modules</FormLabel>
                    <FormControl>
                      <Textarea
                        placeholder='["math", "json", "re", "datetime"]'
                        className="font-mono text-sm min-h-[90px]"
                        {...field}
                      />
                    </FormControl>
                    <FormDescription>JSON array of module names the Python process is permitted to import.</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </CardContent>
          </Card>

          <Card className="border-line bg-panel">
            <CardHeader>
              <CardTitle className="text-subtitle">Resource limits</CardTitle>
              <CardDescription className="font-body text-ui-text text-steel">Specify CPU, time, memory, and output boundaries for code runs</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-6 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="max_wall_time_s"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Max wall time (seconds)</FormLabel>
                    <FormControl>
                      <Input type="number" {...field} />
                    </FormControl>
                    <FormDescription>Maximum total elapsed execution time allowed.</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="max_cpu_seconds"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Max CPU time (seconds)</FormLabel>
                    <FormControl>
                      <Input type="number" {...field} />
                    </FormControl>
                    <FormDescription>Maximum CPU time consumed by the sandboxed process.</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="max_memory_mb"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Max memory (MB)</FormLabel>
                    <FormControl>
                      <Input type="number" {...field} />
                    </FormControl>
                    <FormDescription>Maximum RAM allocation before termination.</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="max_output_bytes"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Max output (bytes)</FormLabel>
                    <FormControl>
                      <Input type="number" {...field} />
                    </FormControl>
                    <FormDescription>Combined stdout/stderr character limit (default 1MB).</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </CardContent>
          </Card>

          <Card className="border-line bg-panel">
            <CardHeader className="flex flex-row items-center justify-between gap-4">
              <div>
                <CardTitle className="text-subtitle">Broker capabilities</CardTitle>
                <CardDescription className="font-body text-ui-text text-steel">Capabilities the sandbox broker may invoke back into Frappe under the acting user's permissions</CardDescription>
              </div>
              <Button type="button" variant="outline" size="sm" onClick={handleAddPermission} className="shrink-0 border-line hover:border-ink hover:bg-paper-deep">
                <Plus className="h-4 w-4 mr-2" />
                Add permission
              </Button>
            </CardHeader>
            <CardContent className="space-y-4">
              {permissions.length === 0 ? (
                <p className="text-sm text-steel">No capabilities granted. Click "Add permission" to allow this profile to call back into Frappe.</p>
              ) : (
                permissions.map((permission, index) => (
                  <ExecutionProfilePermissionCard
                    key={index}
                    permission={permission}
                    index={index}
                    docTypeOptions={docTypeOptions}
                    loadingDocTypes={loadingDocTypes}
                    onChange={handleUpdatePermission}
                    onDelete={handleDeletePermission}
                  />
                ))
              )}
            </CardContent>
          </Card>
        </form>
      </Form>
      </div>
    </div>
  );
}

export default ExecutionProfileFormPage;
