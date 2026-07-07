import { useEffect, useState } from 'react';
import { useNavigate, useParams, useLocation } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { toast } from 'sonner';
import { Form, FormField, FormItem, FormControl, FormMessage } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { Switch } from '@/components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { MoreVertical, Save, Trash2, Copy, GitFork } from 'lucide-react';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { InstructionsTextarea } from '@/components/agent/InstructionsTextarea';
import { AgentPromptNewVersionDialog } from '@/components/agent/AgentPromptNewVersionDialog';
import {
  createAgentSummaryPrompt,
  createAgentSummaryPromptNewVersion,
  deleteAgentSummaryPrompt,
  forkAgentSummaryPrompt,
  getAgentSummaryPrompt,
  getAgentSummaryPromptUsageCount,
  getAgentsUsingSummaryPrompt,
  updateAgentSummaryPrompt,
  type AgentSummaryPromptDoc,
  type AgentSummaryPromptUsageAgent,
} from '@/services/agentSummaryPromptApi';

const agentSummaryPromptFormSchema = z.object({
  title: z.string().min(1, 'Title is required'),
  slug: z.string().optional(),
  description: z.string().optional(),
  is_active: z.boolean().default(true),
  visibility: z.enum(['Public', 'App', 'Private']).default('Private'),
  tags: z.string().optional(),
  prompt_body: z.string().min(1, 'Prompt body is required'),
});

type AgentSummaryPromptFormValues = z.infer<typeof agentSummaryPromptFormSchema>;

function mapDocToFormValues(doc: AgentSummaryPromptDoc): AgentSummaryPromptFormValues {
  return {
    title: doc.title || '',
    slug: doc.slug || '',
    description: doc.description || '',
    is_active: doc.is_active === 1,
    visibility: doc.visibility || 'Private',
    tags: doc.tags || '',
    prompt_body: doc.prompt_body || '',
  };
}

export function AgentSummaryPromptFormPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const isNew = id === 'new';
  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);
  const [usageCount, setUsageCount] = useState(0);
  const [usageAgents, setUsageAgents] = useState<AgentSummaryPromptUsageAgent[]>([]);
  const [docMeta, setDocMeta] = useState<Pick<
    AgentSummaryPromptDoc,
    'name' | 'version' | 'is_latest' | 'previous_version' | 'forked_from'
  > | null>(null);
  const [newVersionDialogOpen, setNewVersionDialogOpen] = useState(false);
  const [newVersionTitle, setNewVersionTitle] = useState('');
  const [newVersionDescription, setNewVersionDescription] = useState('');
  const [dialogAction, setDialogAction] = useState<'new-version' | 'fork'>('new-version');

  const form = useForm<AgentSummaryPromptFormValues>({
    resolver: zodResolver(agentSummaryPromptFormSchema),
    defaultValues: {
      title: '',
      slug: '',
      description: '',
      is_active: true,
      visibility: 'Private',
      tags: '',
      prompt_body: '',
    },
  });

  useEffect(() => {
    if (!id || isNew) {
      const state = location.state as {
        prefill?: Partial<AgentSummaryPromptFormValues>;
        previous_version?: string;
        forked_from?: string;
        current_version?: number;
      } | null;

      if (state?.prefill) {
        form.reset({
          ...form.getValues(),
          ...state.prefill,
        });
      }
      if (state?.previous_version || state?.forked_from) {
        setDocMeta({
          name: '',
          version: state.previous_version && state.current_version ? state.current_version + 1 : 1,
          is_latest: 1,
          previous_version: state.previous_version,
          forked_from: state.forked_from,
        });
      }

      setLoading(false);
      return;
    }

    let cancelled = false;
    const loadPrompt = async () => {
      try {
        const prompt = await getAgentSummaryPrompt(id);
        if (cancelled) return;

        form.reset(mapDocToFormValues(prompt));
        setDocMeta({
          name: prompt.name,
          version: prompt.version,
          is_latest: prompt.is_latest,
          previous_version: prompt.previous_version,
        });

        const [count, agents] = await Promise.all([
          getAgentSummaryPromptUsageCount(prompt.name),
          getAgentsUsingSummaryPrompt(prompt.name),
        ]);
        if (cancelled) return;
        setUsageCount(count);
        setUsageAgents(agents);
      } catch (error) {
        toast.error('Failed to load Agent Summary Prompt', {
          description: getFrappeErrorMessage(error),
        });
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    loadPrompt();
    return () => {
      cancelled = true;
    };
  }, [id, isNew, form, location.state]);

  const watchedTitle = form.watch('title');
  useEffect(() => {
    if (isNew && watchedTitle) {
      const slug = watchedTitle
        .toLowerCase()
        .replace(/[^\w\s-]/g, '')
        .replace(/\s+/g, '-')
        .replace(/-+/g, '-')
        .replace(/^-|-$/g, '');
      form.setValue('slug', slug, { shouldDirty: true });
    }
  }, [watchedTitle, isNew, form]);

  const handleSave = form.handleSubmit(
    async (values) => {
      setSaving(true);
      try {
        const payload: Partial<AgentSummaryPromptDoc> = {
          title: values.title,
          slug: values.slug || undefined,
          description: values.description || undefined,
          is_active: values.is_active ? 1 : 0,
          visibility: values.visibility,
          tags: values.tags || undefined,
          prompt_body: values.prompt_body,
        };

        if (isNew && docMeta?.previous_version) {
          payload.previous_version = docMeta.previous_version;
        }
        if (isNew && docMeta?.forked_from) {
          payload.forked_from = docMeta.forked_from;
        }

        if (isNew) {
          const created = await createAgentSummaryPrompt(payload);
          toast.success('Agent Summary Prompt created');

          const state = location.state as { returnTo?: string; selectedPromptField?: string } | null;
          const fallbackRaw = (() => {
            try {
              return localStorage.getItem('agentSummaryPromptCreateReturnTo');
            } catch {
              return null;
            }
          })();
          const fallback = fallbackRaw
            ? (JSON.parse(fallbackRaw) as { returnTo?: string; selectedPromptField?: string })
            : null;

          const returnTo = state?.returnTo || fallback?.returnTo;
          const selectedPromptField = state?.selectedPromptField || fallback?.selectedPromptField;

          if (returnTo) {
            navigate(returnTo, {
              state: {
                selectedPrompt: created.name,
                showTab: 'advanced',
                selectedPromptField,
              },
              replace: true,
            });

            try {
              localStorage.removeItem('agentSummaryPromptCreateReturnTo');
            } catch {
              // ignore
            }
            return;
          }

          navigate(`/summary-prompts/${created.name}`);
          return;
        }

        if (!id) return;
        const updated = await updateAgentSummaryPrompt(id, payload);
        form.reset(mapDocToFormValues(updated));
        setDocMeta({
          name: updated.name,
          version: updated.version,
          is_latest: updated.is_latest,
          previous_version: updated.previous_version,
        });
        toast.success('Agent Summary Prompt saved');

        const state = location.state as { returnTo?: string; selectedPromptField?: string } | null;
        const fallbackRaw = (() => {
          try {
            return localStorage.getItem('agentSummaryPromptCreateReturnTo');
          } catch {
            return null;
          }
        })();
        const fallback = fallbackRaw
          ? (JSON.parse(fallbackRaw) as { returnTo?: string; selectedPromptField?: string })
          : null;

        const returnTo = state?.returnTo || fallback?.returnTo;
        const selectedPromptField = state?.selectedPromptField || fallback?.selectedPromptField;

        if (returnTo) {
          navigate(returnTo, {
            state: {
              selectedPrompt: updated.name,
              showTab: 'advanced',
              selectedPromptField,
            },
            replace: true,
          });

          try {
            localStorage.removeItem('agentSummaryPromptCreateReturnTo');
          } catch {
            // ignore
          }
          return;
        }
      } catch (error) {
        toast.error('Failed to save Agent Summary Prompt', {
          description: getFrappeErrorMessage(error),
        });
      } finally {
        setSaving(false);
      }
    },
    (errors) => {
      if (errors.title) {
        toast.error(errors.title.message || 'Title is required');
      } else {
        toast.error('Please check the form for errors');
      }
    }
  );

  const handleCreateNewVersion = () => {
    const currentValues = form.getValues();
    setDialogAction('new-version');
    setNewVersionTitle(currentValues.title || '');
    setNewVersionDescription(currentValues.description || '');
    setNewVersionDialogOpen(true);
  };

  const handleConfirmCreateNewVersion = async () => {
    if (!docMeta?.name) return;

    const currentValues = form.getValues();
    try {
      setSaving(true);
      const result = await createAgentSummaryPromptNewVersion(
        docMeta.name,
        currentValues.prompt_body,
        newVersionTitle?.trim() || currentValues.title,
        newVersionDescription?.trim() || undefined
      );
      toast.success(`Created version ${result.version}`);
      setNewVersionDialogOpen(false);
      navigate(`/summary-prompts/${result.name}`);
    } catch (error) {
      toast.error('Failed to create new version', {
        description: getFrappeErrorMessage(error),
      });
    } finally {
      setSaving(false);
    }
  };

  const handleForkPrompt = () => {
    const currentValues = form.getValues();
    setDialogAction('fork');
    setNewVersionTitle(`Copy of ${currentValues.title}`);
    setNewVersionDescription('');
    setNewVersionDialogOpen(true);
  };

  const handleConfirmForkPrompt = async () => {
    if (!docMeta?.name) return;
    try {
      setSaving(true);
      const result = await forkAgentSummaryPrompt(docMeta.name, newVersionTitle?.trim() || undefined);
      toast.success('Summary prompt forked successfully');
      setNewVersionDialogOpen(false);
      navigate(`/summary-prompts/${result.name}`);
    } catch (error) {
      toast.error('Failed to fork summary prompt', {
        description: getFrappeErrorMessage(error),
      });
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!id || isNew) return;
    if (!window.confirm('Delete this Agent Summary Prompt?')) return;

    try {
      await deleteAgentSummaryPrompt(id);
      toast.success('Agent Summary Prompt deleted');
      navigate('/summary-prompts');
    } catch (error) {
      toast.error('Failed to delete Agent Summary Prompt', {
        description: getFrappeErrorMessage(error),
      });
    }
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-muted-foreground">Loading Agent Summary Prompt...</div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto">
      <div className="p-6 space-y-6 max-w-6xl mx-auto">
        <Form {...form}>
          <form onSubmit={handleSave} className="space-y-6">
            <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
              <div className="space-y-2">
                <FormField
                  control={form.control}
                  name="title"
                  render={({ field }) => (
                    <FormItem className="space-y-0">
                      <FormControl>
                        <Input
                          {...field}
                          className="text-2xl font-bold h-auto border-0 px-0 focus-visible:ring-0 max-w-2xl error:border-destructive"
                          placeholder="Summary Prompt Title"
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={form.watch('is_active') ? 'default' : 'secondary'}>
                    {form.watch('is_active') ? 'Active' : 'Inactive'}
                  </Badge>
                  <Badge variant="outline">{form.watch('visibility')}</Badge>
                  {!isNew ? (
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          type="button"
                          variant={form.watch('is_active') ? 'default' : 'secondary'}
                          size="sm"
                          className="h-6 rounded-full px-2 text-xs"
                        >
                          Used by {usageCount} {usageCount === 1 ? 'agent' : 'agents'}
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="start" className="w-72">
                        {usageAgents.length === 0 ? (
                          <DropdownMenuItem disabled>No agents found.</DropdownMenuItem>
                        ) : (
                          usageAgents.map((agent) => (
                            <DropdownMenuItem key={agent.name} onClick={() => navigate(`/agents/${agent.name}`)}>
                              {agent.agent_name || agent.name}
                            </DropdownMenuItem>
                          ))
                        )}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  ) : null}
                </div>
              </div>

              <div className="flex items-center gap-2">
                <Button size="sm" type="submit" disabled={saving}>
                  <Save className="mr-2 h-4 w-4" />
                  {saving ? (isNew ? 'Creating...' : 'Saving...') : isNew ? 'Create' : 'Save'}
                </Button>
                {!isNew ? (
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="outline" size="sm" type="button">
                        <MoreVertical className="h-4 w-4" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem onClick={handleCreateNewVersion}>
                        <Copy className="mr-2 h-4 w-4" />
                        Create New Version
                      </DropdownMenuItem>
                      <DropdownMenuItem onClick={handleForkPrompt}>
                        <GitFork className="mr-2 h-4 w-4" />
                        Fork Prompt
                      </DropdownMenuItem>
                      <DropdownMenuItem className="text-destructive" onClick={handleDelete}>
                        <Trash2 className="mr-2 h-4 w-4" />
                        Delete
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                ) : null}
              </div>
            </div>

            <Card>
              <CardHeader>
                <CardTitle>Summary Prompt Details</CardTitle>
              </CardHeader>
              <CardContent className="grid gap-4 sm:grid-cols-2">
                <FormField
                  control={form.control}
                  name="title"
                  render={({ field }) => (
                    <FormItem className="space-y-2 sm:col-span-2">
                      <Label>Title</Label>
                      <FormControl>
                        <Input {...field} placeholder="Summary prompt title" />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <div className="space-y-2">
                  <Label htmlFor="slug">Slug</Label>
                  <Input
                    id="slug"
                    value={form.watch('slug') || ''}
                    onChange={(event) => form.setValue('slug', event.target.value, { shouldDirty: true })}
                    placeholder="Auto-generated from title"
                    disabled={!isNew}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Visibility</Label>
                  <Select
                    value={form.watch('visibility')}
                    onValueChange={(value) =>
                      form.setValue('visibility', value as AgentSummaryPromptFormValues['visibility'], {
                        shouldDirty: true,
                      })
                    }
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select visibility" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="Private">Private</SelectItem>
                      <SelectItem value="App">App</SelectItem>
                      <SelectItem value="Public">Public</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2 sm:col-span-2">
                  <Label htmlFor="description">Description</Label>
                  <Textarea
                    id="description"
                    value={form.watch('description') || ''}
                    onChange={(event) => form.setValue('description', event.target.value, { shouldDirty: true })}
                    placeholder="Describe what this summary prompt is for"
                    rows={3}
                  />
                </div>
                <div className="space-y-2 sm:col-span-2">
                  <Label htmlFor="tags">Tags</Label>
                  <Input
                    id="tags"
                    value={form.watch('tags') || ''}
                    onChange={(event) => form.setValue('tags', event.target.value, { shouldDirty: true })}
                    placeholder="Comma-separated tags"
                  />
                </div>
                <div className="flex flex-row items-center justify-between rounded-lg border p-4 sm:col-span-2">
                  <div className="space-y-0.5">
                    <Label className="text-base">Active</Label>
                  </div>
                  <Switch
                    checked={form.watch('is_active')}
                    onCheckedChange={(checked) => form.setValue('is_active', checked, { shouldDirty: true })}
                  />
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Prompt Body</CardTitle>
              </CardHeader>
              <CardContent>
                <InstructionsTextarea
                  value={form.watch('prompt_body')}
                  onChange={(value) => form.setValue('prompt_body', value, { shouldDirty: true })}
                  placeholder="Write the summary prompt here. Use {summary_data} as a placeholder for the JSON input."
                  className="min-h-[340px] font-mono resize-y"
                  showOptimize={false}
                  showExpand
                />
              </CardContent>
            </Card>

            {!isNew && docMeta ? (
              <Card>
                <CardHeader>
                  <CardTitle>Version Info</CardTitle>
                </CardHeader>
                <CardContent className="flex flex-wrap gap-2">
                  <Badge variant="outline">Version {docMeta.version ?? 1}</Badge>
                  {docMeta.is_latest === 1 ? <Badge>Latest</Badge> : <Badge variant="secondary">Historical</Badge>}
                  {docMeta.previous_version ? (
                    <Button
                      variant="link"
                      className="h-auto p-0"
                      onClick={() => navigate(`/summary-prompts/${docMeta.previous_version}`)}
                    >
                      Previous: {docMeta.previous_version}
                    </Button>
                  ) : null}
                </CardContent>
              </Card>
            ) : null}
          </form>
          <AgentPromptNewVersionDialog
            open={newVersionDialogOpen}
            onOpenChange={setNewVersionDialogOpen}
            dialogTitle={dialogAction === 'fork' ? 'Fork Summary Prompt' : 'Create New Version'}
            title={newVersionTitle}
            description={newVersionDescription}
            showDescription={dialogAction !== 'fork'}
            titleLabel={dialogAction === 'fork' ? 'Title for Fork' : 'Title (Optional)'}
            onTitleChange={setNewVersionTitle}
            onDescriptionChange={setNewVersionDescription}
            onConfirm={dialogAction === 'fork' ? handleConfirmForkPrompt : handleConfirmCreateNewVersion}
            confirmLabel={dialogAction === 'fork' ? 'Fork' : 'Create'}
            saving={saving}
          />
        </Form>
      </div>
    </div>
  );
}

export default AgentSummaryPromptFormPage;
