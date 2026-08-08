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
import { Save, Trash2, ShieldCheck, Loader2 } from 'lucide-react';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import {
  createExecutionProfile,
  deleteExecutionProfile,
  getExecutionProfile,
  updateExecutionProfile,
  type ExecutionProfileDoc,
} from '@/services/executionProfileApi';
import { InlineEditName } from '@/components/common/InlineEditName';

const executionProfileSchema = z.object({
  profile_name: z.string().min(1, 'Profile name is required'),
  disabled: z.boolean().default(false),
  approval_mode: z.enum(['Auto Approve', 'Ask Every Time', 'Never Allow']).default('Ask Every Time'),
  filesystem_policy: z.enum(['None', 'Scratch Only', 'Shared Directory']).default('None'),
  allowed_modules: z.string().optional(),
  max_wall_time_s: z.coerce.number().min(1, 'Wall time limit must be at least 1s').default(30),
  max_cpu_seconds: z.coerce.number().min(1, 'CPU limit must be at least 1s').default(30),
  max_memory_mb: z.coerce.number().min(1, 'Memory limit must be at least 1MB').default(256),
  max_output_bytes: z.coerce.number().min(1024, 'Output limit must be at least 1024 bytes').default(1048576),
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

  const form = useForm<ExecutionProfileFormValues>({
    resolver: zodResolver(executionProfileSchema),
    defaultValues: {
      profile_name: '',
      disabled: false,
      approval_mode: 'Ask Every Time',
      filesystem_policy: 'None',
      allowed_modules: '["math", "json", "re", "datetime", "random", "typing"]',
      max_wall_time_s: 30,
      max_cpu_seconds: 30,
      max_memory_mb: 256,
      max_output_bytes: 1048576,
    },
  });

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
          allowed_modules: profile.allowed_modules || '[]',
          max_wall_time_s: profile.max_wall_time_s ?? 30,
          max_cpu_seconds: profile.max_cpu_seconds ?? 30,
          max_memory_mb: profile.max_memory_mb ?? 256,
          max_output_bytes: profile.max_output_bytes ?? 1048576,
        });
      } catch (error) {
        toast.error('Failed to load Execution Profile', {
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

  const onSubmit = async (values: ExecutionProfileFormValues) => {
    setSaving(true);
    try {
      const payload: Partial<ExecutionProfileDoc> = {
        profile_name: values.profile_name,
        disabled: values.disabled ? 1 : 0,
        approval_mode: values.approval_mode,
        filesystem_policy: values.filesystem_policy,
        allowed_modules: values.allowed_modules,
        max_wall_time_s: values.max_wall_time_s,
        max_cpu_seconds: values.max_cpu_seconds,
        max_memory_mb: values.max_memory_mb,
        max_output_bytes: values.max_output_bytes,
      };

      if (isNew) {
        const created = await createExecutionProfile(payload);
        toast.success('Execution Profile created successfully');
        handleReturnNavigation(created.name || created.profile_name);
      } else {
        const updated = await updateExecutionProfile(id!, payload);
        toast.success('Execution Profile updated successfully');
        setProfileDoc(updated);
      }
    } catch (error) {
      toast.error(isNew ? 'Failed to create Execution Profile' : 'Failed to update Execution Profile', {
        description: getFrappeErrorMessage(error),
      });
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!id || isNew) return;
    if (!confirm('Are you sure you want to delete this Execution Profile?')) return;

    setDeleting(true);
    try {
      await deleteExecutionProfile(id);
      toast.success('Execution Profile deleted');
      navigate('/execution-profiles');
    } catch (error) {
      toast.error('Failed to delete Execution Profile', {
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
    <div className="flex-1 overflow-y-auto">
      <div className="space-y-6 max-w-4xl mx-auto p-6 pb-12">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-start gap-3">
          <ShieldCheck className="h-8 w-8 text-steel-soft shrink-0 mt-1" strokeWidth={1.6} />
          <div>
            <InlineEditName
              value={form.watch('profile_name') || (isNew ? 'New Execution Profile' : id!)}
              onChange={(name: string) => form.setValue('profile_name', name, { shouldDirty: true })}
              placeholder="Profile Name"
              className="[&_h1]:font-display [&_h1]:text-[34px] [&_h1]:uppercase [&_h1]:leading-tight"
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
              <CardTitle className="font-display font-bold text-[18px] uppercase">General Settings</CardTitle>
              <CardDescription className="font-body text-[13px] text-steel">Configure security policy and sandbox behavior</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <FormField
                control={form.control}
                name="profile_name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Profile Name</FormLabel>
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
                      <FormLabel className="text-base">Disable Profile</FormLabel>
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
                      <FormLabel>Approval Mode</FormLabel>
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
                      <FormLabel>Filesystem Policy</FormLabel>
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
                name="allowed_modules"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Allowed Python Modules</FormLabel>
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
              <CardTitle className="font-display font-bold text-[18px] uppercase">Resource Limits</CardTitle>
              <CardDescription className="font-body text-[13px] text-steel">Specify CPU, time, memory, and output boundaries for code runs</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-6 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="max_wall_time_s"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Max Wall Time (Seconds)</FormLabel>
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
                    <FormLabel>Max CPU Time (Seconds)</FormLabel>
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
                    <FormLabel>Max Memory (MB)</FormLabel>
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
                    <FormLabel>Max Output (Bytes)</FormLabel>
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
        </form>
      </Form>
      </div>
    </div>
  );
}

export default ExecutionProfileFormPage;
