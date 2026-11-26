import { useResourceAccess } from '@/hooks/permissions/useResourceAccess';
import { useEffect, useState } from 'react';
import { useNavigate, useParams, useLocation } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { toast } from 'sonner';
import { Form, FormField, FormItem, FormControl, FormMessage } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { MoreVertical, Save, Trash2, Copy, GitFork } from 'lucide-react';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { InstructionsTextarea } from '@/components/agent/InstructionsTextarea';
import { AgentPromptNewVersionDialog } from '@/components/agent/AgentPromptNewVersionDialog';
import {
  createAgentPrompt,
  createAgentPromptNewVersion,
  deleteAgentPrompt,
  forkAgentPrompt,
  getAgentPrompt,
  getAgentPromptUsageCount,
  getAgentsUsingPrompt,
  updateAgentPrompt,
  type AgentPromptDoc,
  type AgentPromptUsageAgent,
} from '@/services/agentPromptApi';
import { CategoryTab } from '@/components/category/CategoryTab';
import { CategoryModal } from '@/components/category/CategoryModal';
import { getCategories, type CategoryDoc } from '@/services/categoryApi';
import { useSaveShortcut } from '@/hooks/useSaveShortcut';
import { InlineEditName } from '@/components/common/InlineEditName';
import { agentPromptFormSchema, mapDocToFormValues, type AgentPromptFormValues } from '@/components/prompts/promptForm';
import { clearPromptReturn, readPromptReturn, savePrompt } from '@/components/prompts/promptSave';
import { PromptAdvancedFields } from '@/components/prompts/PromptAdvancedFields';
import { PromptVersionInfo } from '@/components/prompts/PromptVersionInfo';

export function AgentPromptFormPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const access = useResourceAccess('prompt');
  const location = useLocation();
  const isNew = id === 'new';
  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);
  const [usageCount, setUsageCount] = useState(0);
  const [usageAgents, setUsageAgents] = useState<AgentPromptUsageAgent[]>([]);
  const [docMeta, setDocMeta] = useState<Pick<
    AgentPromptDoc,
    'name' | 'version' | 'is_latest' | 'previous_version' | 'category' | 'forked_from'
  > | null>(null);
  const [categoryModalOpen, setCategoryModalOpen] = useState(false);
  const [editingCategory, setEditingCategory] = useState<CategoryDoc | null>(null);
  const [selectedCategory, setSelectedCategory] = useState<CategoryDoc | null>(null);
  const [allCategories, setAllCategories] = useState<CategoryDoc[]>([]);
  const [newVersionDialogOpen, setNewVersionDialogOpen] = useState(false);
  const [newVersionTitle, setNewVersionTitle] = useState('');
  const [newVersionDescription, setNewVersionDescription] = useState('');
  const [dialogAction, setDialogAction] = useState<'new-version' | 'fork'>('new-version');

  const readOnly = !isNew && docMeta?.is_latest === 0;

  const form = useForm<AgentPromptFormValues>({
    resolver: zodResolver(agentPromptFormSchema),
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
        prefill?: Partial<AgentPromptFormValues>;
        previous_version?: string;
        forked_from?: string;
        current_version?: number;
        category?: CategoryDoc;
      } | null;
      
      if (state?.prefill) {
        form.reset({
          ...form.getValues(),
          ...state.prefill
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
      if (state?.category) {
        setSelectedCategory(state.category);
      }

      setLoading(false);
      return;
    }

    let cancelled = false;
    const loadPrompt = async () => {
      try {
        const prompt = await getAgentPrompt(id);
        if (cancelled) return;

        form.reset(mapDocToFormValues(prompt));
        setDocMeta({
          name: prompt.name,
          version: prompt.version,
          is_latest: prompt.is_latest,
          previous_version: prompt.previous_version,
          category: prompt.category,
        });

        const [count, agents] = await Promise.all([
          getAgentPromptUsageCount(prompt.name),
          getAgentsUsingPrompt(prompt.name),
        ]);
        if (cancelled) return;
        setUsageCount(count);
        setUsageAgents(agents);
      } catch (error) {
        toast.error('Failed to load Agent Prompt', {
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
  }, [id, isNew, form]);

  useEffect(() => {
    const loadCategories = async () => {
      try {
        const data = await getCategories();
        setAllCategories(data);
      } catch {
        toast.error('Failed to load categories');
      }
    };

    loadCategories();
  }, []);

  // Auto-generate slug from title for new prompts
  useEffect(() => {
    if (isNew && form.watch('title')) {
      const slug = form.watch('title')
        .toLowerCase()
        .replace(/[^\w\s-]/g, '')
        .replace(/\s+/g, '-')
        .replace(/-+/g, '-')
        .replace(/^-|-$/g, '');
      form.setValue('slug', slug, { shouldDirty: true });
    }
  }, [form.watch('title'), isNew, form]);

  // Set selected category when all categories are loaded
  useEffect(() => {
    if (allCategories.length > 0 && docMeta?.category) {
      const match = allCategories.find((c) => c.name === docMeta.category);
      if (match) setSelectedCategory(match);
    }
  }, [allCategories, docMeta?.category]);

  // Auto-save category when it changes
  useEffect(() => {
    if (!docMeta?.name || loading) return;
    // Don't auto-save if selectedCategory is still null but docMeta has a category (not yet loaded)
    if (docMeta.category && !selectedCategory && allCategories.length === 0) return;
    // Only save if the category has actually changed
    if (selectedCategory?.name === docMeta?.category) return;

    const saveCategory = async () => {
      try {
        await updateAgentPrompt(docMeta.name, {
          category: selectedCategory?.name || undefined,
        });
      } catch (error) {
        console.error('Failed to save category:', error);
        toast.error('Failed to save category changes');
      }
    };

    // Debounce the save to avoid too many API calls
    const timeoutId = setTimeout(saveCategory, 500);
    return () => clearTimeout(timeoutId);
  }, [selectedCategory, docMeta?.name, loading, docMeta?.category, allCategories.length]);

  const returnAfterSave = (promptName: string): boolean => {
    const target = readPromptReturn(location.state as { returnTo?: string; selectedPromptField?: string } | null);
    if (!target) return false;
    navigate(target.returnTo, {
      state: { selectedPrompt: promptName, showTab: 'general', selectedPromptField: target.selectedPromptField },
      replace: true,
    });
    clearPromptReturn();
    return true;
  };

  const handleSave = form.handleSubmit(
    async (values) => {
      if (readOnly) return;
      setSaving(true);
      try {
        const payload: Partial<AgentPromptDoc> = {
          title: values.title,
          slug: values.slug || undefined,
          description: values.description || undefined,
          is_active: values.is_active ? 1 : 0,
          visibility: values.visibility,
          tags: values.tags || undefined,
          prompt_body: values.prompt_body,
          category: selectedCategory?.name || undefined,
        };

        if (isNew) {
          if (docMeta?.previous_version) payload.previous_version = docMeta.previous_version;
          if (docMeta?.forked_from) payload.forked_from = docMeta.forked_from;
          const created = await createAgentPrompt(payload);
          toast.success('Agent Prompt created');
          if (!returnAfterSave(created.name)) navigate(`/prompts/${created.name}`);
          return;
        }

        if (!id) return;
        // The server versions a changed body; metadata-only saves update in place.
        const result = await savePrompt(id, payload);
        const updated = await getAgentPrompt(result.name);
        form.reset(mapDocToFormValues(updated));
        setDocMeta({
          name: updated.name,
          version: updated.version,
          is_latest: updated.is_latest,
          previous_version: updated.previous_version,
          category: updated.category,
        });
        toast.success(
          result.versioned ? `Saved as version ${result.version}` : result.changed ? 'Agent Prompt saved' : 'No changes to save'
        );
        if (returnAfterSave(result.name)) return;
        if (result.name !== id) navigate(`/prompts/${result.name}`, { replace: true });
      } catch (error) {
        toast.error('Failed to save Agent Prompt', {
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

  useSaveShortcut({
    onSave: () => { void handleSave(); },
    enabled: !loading,
    isSubmitting: saving,
  });

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
      const result = await createAgentPromptNewVersion(
        docMeta.name,
        currentValues.prompt_body,
        newVersionTitle?.trim() || currentValues.title,
        newVersionDescription?.trim() || undefined
      );
      toast.success(`Created version ${result.version}`);
      setNewVersionDialogOpen(false);
      navigate(`/prompts/${result.name}`);
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
      const result = await forkAgentPrompt(docMeta.name, newVersionTitle?.trim() || undefined);
      toast.success('Prompt forked successfully');
      setNewVersionDialogOpen(false);
      navigate(`/prompts/${result.name}`);
    } catch (error) {
      toast.error('Failed to fork prompt', {
        description: getFrappeErrorMessage(error),
      });
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!id || isNew) return;
    if (!window.confirm('Delete this Agent Prompt?')) return;

    try {
      await deleteAgentPrompt(id);
      toast.success('Agent Prompt deleted');
      navigate('/prompts');
    } catch (error) {
      toast.error('Failed to delete Agent Prompt', {
        description: getFrappeErrorMessage(error),
      });
    }
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="font-body text-steel-soft">Loading Agent Prompt...</div>
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
                        {isNew ? (
                          <Input
                            {...field}
                            className="text-2xl font-bold h-auto border-0 px-0 focus-visible:ring-0 max-w-2xl error:border-destructive"
                            placeholder="e.g. Customer support greeting"
                          />
                        ) : (
                          <InlineEditName
                            value={field.value}
                            onChange={field.onChange}
                            placeholder="e.g. Customer support greeting"
                          />
                        )}
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
                <Button size="sm" type="submit" disabled={saving || readOnly}>
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
                        Create new version
                      </DropdownMenuItem>
                      <DropdownMenuItem onClick={handleForkPrompt}>
                        <GitFork className="mr-2 h-4 w-4" />
                        Fork prompt
                      </DropdownMenuItem>
                      {access.canDelete && (
                      <DropdownMenuItem className="text-destructive" onClick={handleDelete}>
                        <Trash2 className="mr-2 h-4 w-4" />
                        Delete
                      </DropdownMenuItem>
                      )}
                    </DropdownMenuContent>
                  </DropdownMenu>
                ) : null}
              </div>
            </div>

            <CategoryTab
              selectedCategory={selectedCategory}
              onAddCategory={() => {
                setEditingCategory(null);
                setCategoryModalOpen(true);
              }}
              onRemoveCategory={() =>
                setSelectedCategory(null)
              }
              onEditCategory={(category) => {
                setEditingCategory(category);
                setCategoryModalOpen(true);
              }}
            />

            <Card>
              <CardHeader>
                <CardTitle>Prompt body</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-xs text-steel-soft mb-3">
                  The prompt template content. This is the system prompt or instructions text.
                </p>
                <InstructionsTextarea
                  value={form.watch('prompt_body')}
                  onChange={(value) => form.setValue('prompt_body', value, { shouldDirty: true })}
                  placeholder="Write the prompt instructions here"
                  className="min-h-[340px] font-mono resize-y"
                  showOptimize={false}
                  showExpand
                />
              </CardContent>
            </Card>

            <PromptAdvancedFields form={form} isNew={isNew} />

            {!isNew && docMeta ? (
              <PromptVersionInfo
                version={docMeta.version}
                isLatest={docMeta.is_latest}
                previousVersion={docMeta.previous_version}
                onOpenPrevious={(name) => navigate(`/prompts/${name}`)}
              />
            ) : null}
          </form>
          <CategoryModal
            open={categoryModalOpen}
            onOpenChange={(open) => {
              setCategoryModalOpen(open);
              if (!open) setEditingCategory(null);
            }}
            categories={allCategories}
            selected={selectedCategory}
            onSave={setSelectedCategory}
            refreshCategories={async () => {
              const data = await getCategories();
              setAllCategories(data);
            }}
            editCategory={editingCategory}
            onEditComplete={() => setEditingCategory(null)}
          />
          <AgentPromptNewVersionDialog
            open={newVersionDialogOpen}
            onOpenChange={setNewVersionDialogOpen}
            dialogTitle={dialogAction === 'fork' ? 'Fork Prompt' : 'Create New Version'}
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

export default AgentPromptFormPage;
