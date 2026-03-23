import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { toast } from 'sonner';
import { Form } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { Switch } from '@/components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { MoreVertical, Save, Trash2 } from 'lucide-react';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { InstructionsTextarea } from '@/components/agent/InstructionsTextarea';
import {
  createAgentPrompt,
  deleteAgentPrompt,
  getAgentPrompt,
  getAgentPromptUsageCount,
  getAgentsUsingPrompt,
  updateAgentPrompt,
  type AgentPromptDoc,
  type AgentPromptUsageAgent,
} from '@/services/agentPromptApi';

const agentPromptFormSchema = z.object({
  title: z.string().min(1, 'Title is required'),
  slug: z.string().optional(),
  description: z.string().optional(),
  is_active: z.boolean().default(true),
  visibility: z.enum(['Public', 'App', 'Private']).default('Private'),
  tags: z.string().optional(),
  prompt_body: z.string().min(1, 'Prompt body is required'),
});

type AgentPromptFormValues = z.infer<typeof agentPromptFormSchema>;

function mapDocToFormValues(doc: AgentPromptDoc): AgentPromptFormValues {
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

export function AgentPromptFormPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const isNew = id === 'new';
  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);
  const [usageCount, setUsageCount] = useState(0);
  const [usageAgents, setUsageAgents] = useState<AgentPromptUsageAgent[]>([]);
  const [docMeta, setDocMeta] = useState<Pick<
    AgentPromptDoc,
    'name' | 'version' | 'is_latest' | 'previous_version'
  > | null>(null);

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

  const handleSave = form.handleSubmit(async (values) => {
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
      };

      if (isNew) {
        const created = await createAgentPrompt(payload);
        toast.success('Agent Prompt created');
        navigate(`/prompts/${created.name}`);
        return;
      }

      if (!id) return;
      const updated = await updateAgentPrompt(id, payload);
      form.reset(mapDocToFormValues(updated));
      setDocMeta({
        name: updated.name,
        version: updated.version,
        is_latest: updated.is_latest,
        previous_version: updated.previous_version,
      });
      toast.success('Agent Prompt saved');
    } catch (error) {
      toast.error('Failed to save Agent Prompt', {
        description: getFrappeErrorMessage(error),
      });
    } finally {
      setSaving(false);
    }
  });

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
        <div className="text-muted-foreground">Loading Agent Prompt...</div>
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
                <Input
                  value={form.watch('title')}
                  onChange={(event) => form.setValue('title', event.target.value, { shouldDirty: true })}
                  className="text-2xl font-bold h-auto border-0 px-0 focus-visible:ring-0 max-w-2xl"
                  placeholder="Prompt Title"
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
                <CardTitle>Prompt Details</CardTitle>
              </CardHeader>
              <CardContent className="grid gap-4 sm:grid-cols-2">
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
                      form.setValue('visibility', value as AgentPromptFormValues['visibility'], {
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
                    placeholder="Describe what this prompt is for"
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
                  placeholder="Write the prompt instructions here"
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
                      onClick={() => navigate(`/prompts/${docMeta.previous_version}`)}
                    >
                      Previous: {docMeta.previous_version}
                    </Button>
                  ) : null}
                </CardContent>
              </Card>
            ) : null}
          </form>
        </Form>
      </div>
    </div>
  );
}

export default AgentPromptFormPage;
