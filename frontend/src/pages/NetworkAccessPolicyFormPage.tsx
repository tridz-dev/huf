import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useForm, useFieldArray } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { toast } from 'sonner';
import { Plus, Save, Trash2, ShieldCheck, Loader2 } from 'lucide-react';
import { UnifiedLayout } from '@/layouts/UnifiedLayout';
import { Form, FormField, FormItem, FormLabel, FormControl, FormDescription, FormMessage } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { InlineEditName } from '@/components/common/InlineEditName';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import {
  createNetworkAccessPolicy,
  deleteNetworkAccessPolicy,
  getNetworkAccessPolicy,
  updateNetworkAccessPolicy,
  type NetworkAccessPolicyDoc,
} from '@/services/networkAccessPolicyApi';

const networkAccessPolicyRuleSchema = z.object({
  name: z.string().optional(),
  host_or_cidr: z.string().min(1, 'Host or CIDR is required'),
  port_range: z.string().optional(),
  protocol: z.enum(['https', 'http', 'tcp']).default('https'),
});

const networkAccessPolicySchema = z.object({
  policy_name: z.string().min(1, 'Policy name is required'),
  rules: z.array(networkAccessPolicyRuleSchema).default([]),
});

type NetworkAccessPolicyFormValues = z.infer<typeof networkAccessPolicySchema>;

export function NetworkAccessPolicyFormPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const isNew = id === 'new';
  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [policyDoc, setPolicyDoc] = useState<NetworkAccessPolicyDoc | null>(null);

  const form = useForm<NetworkAccessPolicyFormValues>({
    resolver: zodResolver(networkAccessPolicySchema),
    defaultValues: {
      policy_name: '',
      rules: [],
    },
  });

  const { fields, append, remove } = useFieldArray({
    control: form.control,
    name: 'rules',
  });

  useEffect(() => {
    if (isNew) {
      setLoading(false);
      return;
    }

    let cancelled = false;
    const loadPolicy = async () => {
      try {
        const policy = await getNetworkAccessPolicy(id!);
        if (cancelled) return;

        setPolicyDoc(policy);
        form.reset({
          policy_name: policy.policy_name || policy.name,
          rules: (policy.rules || []).map((rule) => ({
            name: rule.name,
            host_or_cidr: rule.host_or_cidr,
            port_range: rule.port_range || '',
            protocol: rule.protocol || 'https',
          })),
        });
      } catch (error) {
        toast.error('Failed to load network access policy', {
          description: getFrappeErrorMessage(error),
        });
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    loadPolicy();
    return () => {
      cancelled = true;
    };
  }, [id, isNew, form]);

  const onSubmit = async (values: NetworkAccessPolicyFormValues) => {
    setSaving(true);
    try {
      const payload: Partial<NetworkAccessPolicyDoc> = {
        policy_name: values.policy_name,
        rules: values.rules,
      };

      if (isNew) {
        const created = await createNetworkAccessPolicy(payload);
        toast.success('Network access policy created');
        navigate(`/network-policies/${created.name}`);
      } else {
        const updated = await updateNetworkAccessPolicy(id!, payload);
        toast.success('Network access policy updated');
        setPolicyDoc(updated);
        if (updated.name !== id) {
          navigate(`/network-policies/${updated.name}`, { replace: true });
        } else {
          form.reset({
            policy_name: updated.policy_name || updated.name,
            rules: (updated.rules || []).map((rule) => ({
              name: rule.name,
              host_or_cidr: rule.host_or_cidr,
              port_range: rule.port_range || '',
              protocol: rule.protocol || 'https',
            })),
          });
        }
      }
    } catch (error) {
      toast.error(isNew ? 'Failed to create network access policy' : 'Failed to update network access policy', {
        description: getFrappeErrorMessage(error),
      });
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!id || isNew) return;
    if (!confirm('Are you sure you want to delete this network access policy?')) return;

    setDeleting(true);
    try {
      await deleteNetworkAccessPolicy(id);
      toast.success('Network access policy deleted');
      navigate('/network-policies');
    } catch (error) {
      toast.error('Failed to delete network access policy', {
        description: getFrappeErrorMessage(error),
      });
    } finally {
      setDeleting(false);
    }
  };

  const policyTitle = form.watch('policy_name') || policyDoc?.policy_name || (isNew ? 'New network access policy' : id || '');

  const breadcrumbs = [
    { label: 'Network access policies', href: '/network-policies' },
    { label: isNew ? 'New policy' : policyTitle },
  ];

  if (loading) {
    return (
      <UnifiedLayout breadcrumbs={breadcrumbs}>
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-8 w-8 animate-spin text-steel-soft" />
        </div>
      </UnifiedLayout>
    );
  }

  return (
    <UnifiedLayout breadcrumbs={breadcrumbs}>
      <div className="flex-1 overflow-y-auto">
        <div className="space-y-6 max-w-4xl mx-auto p-6 pb-12">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-start gap-3">
              <ShieldCheck className="h-8 w-8 text-steel-soft shrink-0 mt-1" strokeWidth={1.6} />
              <div>
                <InlineEditName
                  value={form.watch('policy_name') || (isNew ? 'New network access policy' : id!)}
                  onChange={(name: string) => form.setValue('policy_name', name, { shouldDirty: true })}
                  placeholder="e.g. Internal services only"
                  className="[&_h1]:font-display [&_h1]:text-[34px] [&_h1]:leading-tight"
                />
                <p className="font-mono text-[12px] text-steel mt-1">
                  {isNew ? 'Create a new network access policy' : `ID ${id}`}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              {!isNew && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleDelete}
                  disabled={deleting || saving}
                  className="border-line hover:border-ink hover:bg-paper-deep"
                >
                  {deleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4 text-destructive" />}
                </Button>
              )}
              <Button onClick={form.handleSubmit(onSubmit)} disabled={saving}>
                {saving ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Save className="h-4 w-4 mr-2" />}
                {isNew ? 'Create policy' : 'Save changes'}
              </Button>
            </div>
          </div>

          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
              <Card className="border-line bg-panel">
                <CardHeader>
                  <CardTitle className="text-subtitle">General settings</CardTitle>
                  <CardDescription className="font-body text-ui-text text-steel">
                    Name this policy so it can be applied to connections and execution profiles.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  <FormField
                    control={form.control}
                    name="policy_name"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Policy name</FormLabel>
                        <FormControl>
                          <Input placeholder="e.g. Internal services only" {...field} />
                        </FormControl>
                        <FormDescription>Unique name identifying this network access policy.</FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </CardContent>
              </Card>

              <Card className="border-line bg-panel">
                <CardHeader>
                  <CardTitle className="text-subtitle">Rules</CardTitle>
                  <CardDescription className="font-body text-ui-text text-steel">
                    Define the hosts, ports, and protocols this policy allows.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {fields.length === 0 ? (
                    <p className="text-sm text-muted-foreground mb-4">No rules configured yet.</p>
                  ) : (
                    <div className="space-y-4 mb-4">
                      {fields.map((field, index) => (
                        <div
                          key={field.id}
                          className="grid gap-4 rounded-lg border border-line p-4 md:grid-cols-[2fr_1fr_1fr_auto]"
                        >
                          <FormField
                            control={form.control}
                            name={`rules.${index}.host_or_cidr`}
                            render={({ field: f }) => (
                              <FormItem>
                                <FormLabel>Host / CIDR</FormLabel>
                                <FormControl>
                                  <Input {...f} placeholder="api.example.com or 10.0.0.0/8" />
                                </FormControl>
                                <FormMessage />
                              </FormItem>
                            )}
                          />
                          <FormField
                            control={form.control}
                            name={`rules.${index}.port_range`}
                            render={({ field: f }) => (
                              <FormItem>
                                <FormLabel>Port range</FormLabel>
                                <FormControl>
                                  <Input {...f} placeholder="443 or 1000-2000" />
                                </FormControl>
                                <FormMessage />
                              </FormItem>
                            )}
                          />
                          <FormField
                            control={form.control}
                            name={`rules.${index}.protocol`}
                            render={({ field: f }) => (
                              <FormItem>
                                <FormLabel>Protocol</FormLabel>
                                <Select onValueChange={f.onChange} value={f.value}>
                                  <FormControl>
                                    <SelectTrigger>
                                      <SelectValue placeholder="Select protocol" />
                                    </SelectTrigger>
                                  </FormControl>
                                  <SelectContent>
                                    <SelectItem value="https">https</SelectItem>
                                    <SelectItem value="http">http</SelectItem>
                                    <SelectItem value="tcp">tcp</SelectItem>
                                  </SelectContent>
                                </Select>
                                <FormMessage />
                              </FormItem>
                            )}
                          />
                          <div className="flex items-end">
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              onClick={() => remove(index)}
                              className="text-destructive hover:text-destructive"
                            >
                              <Trash2 className="w-4 h-4" />
                            </Button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => append({ host_or_cidr: '', port_range: '', protocol: 'https' })}
                  >
                    <Plus className="w-4 h-4 mr-2" />
                    Add rule
                  </Button>
                </CardContent>
              </Card>
            </form>
          </Form>
        </div>
      </div>
    </UnifiedLayout>
  );
}

export default NetworkAccessPolicyFormPage;
