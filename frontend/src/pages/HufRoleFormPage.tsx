import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { toast } from 'sonner';
import { ShieldCheck, Lock, Save, Loader2 } from 'lucide-react';
import { UnifiedLayout } from '@/layouts/UnifiedLayout';
import { Form, FormField, FormItem, FormLabel, FormControl, FormDescription, FormMessage } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { MultiSelectCombobox, type MultiSelectComboboxOption } from '@/components/ui/multi-select-combobox';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import {
  getHufRoles,
  getCapabilitiesCatalogue,
  createHufRole,
  updateHufRole,
  type HufRole,
} from '@/services/permissionsApi';

const hufRoleSchema = z.object({
  role_name: z.string().min(1, 'Role name is required'),
  description: z.string().optional(),
  capabilities: z.array(z.string()).default([]),
});

type HufRoleFormValues = z.infer<typeof hufRoleSchema>;

export function HufRoleFormPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const isNew = id === 'new';
  const roleName = isNew ? undefined : decodeURIComponent(id ?? '');

  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);
  const [capabilitiesCatalogue, setCapabilitiesCatalogue] = useState<Record<string, string>>({});
  const [capabilitiesLoading, setCapabilitiesLoading] = useState(true);
  const [existingRole, setExistingRole] = useState<HufRole | null>(null);
  const [existingRoleNames, setExistingRoleNames] = useState<string[]>([]);

  const form = useForm<HufRoleFormValues>({
    resolver: zodResolver(hufRoleSchema),
    defaultValues: {
      role_name: '',
      description: '',
      capabilities: [],
    },
  });

  const isSystemRole = existingRole?.is_system_role === 1;
  const readOnly = !isNew && isSystemRole;

  useEffect(() => {
    getCapabilitiesCatalogue()
      .then(setCapabilitiesCatalogue)
      .finally(() => setCapabilitiesLoading(false));
  }, []);

  useEffect(() => {
    let cancelled = false;

    getHufRoles().then((roles) => {
      if (cancelled) return;
      setExistingRoleNames(roles.map((role) => role.role_name));

      if (isNew) {
        setLoading(false);
        return;
      }

      const found = roles.find((role) => role.role_name === roleName);
      if (found) {
        setExistingRole(found);
        form.reset({
          role_name: found.role_name,
          description: found.description || '',
          capabilities: found.capabilities || [],
        });
      } else {
        toast.error('Role not found');
      }
      setLoading(false);
    });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, isNew]);

  const capabilityOptions: MultiSelectComboboxOption[] = useMemo(
    () =>
      Object.entries(capabilitiesCatalogue).map(([value, label]) => ({
        value,
        label,
      })),
    [capabilitiesCatalogue],
  );

  const onSubmit = async (values: HufRoleFormValues) => {
    setSaving(true);
    try {
      if (isNew) {
        if (existingRoleNames.includes(values.role_name)) {
          form.setError('role_name', { message: 'A role with this name already exists' });
          setSaving(false);
          return;
        }
        const created = await createHufRole(values.role_name, values.description || '', values.capabilities);
        if (created) {
          toast.success('Role created');
          navigate(`/roles/${encodeURIComponent(created.role_name)}`);
        } else {
          toast.error('Failed to create role');
        }
      } else if (roleName) {
        const updated = await updateHufRole(roleName, values.capabilities, values.description);
        if (updated) {
          toast.success('Role updated');
          setExistingRole(updated);
        } else {
          toast.error('Failed to update role');
        }
      }
    } catch (error) {
      toast.error(isNew ? 'Failed to create role' : 'Failed to update role', {
        description: getFrappeErrorMessage(error),
      });
    } finally {
      setSaving(false);
    }
  };

  const breadcrumbs = [
    { label: 'Roles', href: '/members?view=roles' },
    { label: isNew ? 'New role' : roleName || '' },
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
                <h1 className="font-display text-[34px] leading-tight text-ink flex items-center gap-2">
                  {isNew ? 'New role' : roleName}
                  {isSystemRole && <Lock className="h-5 w-5 text-steel-soft" />}
                </h1>
                <p className="font-mono text-[12px] text-steel mt-1">
                  {isNew
                    ? 'Create a new role and choose the capabilities it grants'
                    : isSystemRole
                      ? 'System role — capabilities are fixed and cannot be edited'
                      : 'Edit this role’s description and capabilities'}
                </p>
              </div>
            </div>

            {!readOnly && (
              <Button onClick={form.handleSubmit(onSubmit)} disabled={saving}>
                {saving ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Save className="h-4 w-4 mr-2" />}
                {isNew ? 'Create role' : 'Save changes'}
              </Button>
            )}
          </div>

          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
              <Card className="border-line bg-panel">
                <CardHeader>
                  <CardTitle className="text-subtitle">General</CardTitle>
                  <CardDescription className="font-body text-ui-text text-steel">
                    Name and describe this role
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  <FormField
                    control={form.control}
                    name="role_name"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Role name</FormLabel>
                        <FormControl>
                          <Input placeholder="e.g. Support Lead" {...field} disabled={!isNew} />
                        </FormControl>
                        <FormDescription>
                          {isNew
                            ? 'A unique name for this role. This cannot be changed later.'
                            : 'Role names cannot be changed after creation.'}
                        </FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="description"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Description</FormLabel>
                        <FormControl>
                          <Textarea
                            placeholder="What this role is for and who should have it"
                            className="min-h-[90px]"
                            {...field}
                            disabled={readOnly}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </CardContent>
              </Card>

              <Card className="border-line bg-panel">
                <CardHeader>
                  <CardTitle className="text-subtitle">Capabilities</CardTitle>
                  <CardDescription className="font-body text-ui-text text-steel">
                    Choose what people with this role are allowed to do
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <FormField
                    control={form.control}
                    name="capabilities"
                    render={({ field }) => (
                      <FormItem>
                        <FormControl>
                          <MultiSelectCombobox
                            options={capabilityOptions}
                            values={field.value || []}
                            onValuesChange={field.onChange}
                            placeholder={capabilitiesLoading ? 'Loading capabilities...' : 'Select capabilities'}
                            searchPlaceholder="Search capabilities..."
                            emptyText="No capabilities found."
                            disabled={capabilitiesLoading || readOnly}
                          />
                        </FormControl>
                        <FormDescription>
                          Capabilities determine which pages and actions are available to people with this role.
                        </FormDescription>
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
    </UnifiedLayout>
  );
}

export default HufRoleFormPage;
