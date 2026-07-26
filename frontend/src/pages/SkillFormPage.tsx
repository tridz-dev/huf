import { useEffect, useMemo, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { toast } from 'sonner';
import {
  Form,
  FormField,
  FormItem,
  FormLabel,
  FormControl,
  FormMessage,
  FormDescription,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Combobox } from '@/components/ui/combobox';
import { Plus, Trash2, Server, BookOpen, ScrollText, Plug, Save, Sparkles, Download } from 'lucide-react';
import { getSkill, createSkill, updateSkill, exportSkillAsHuf } from '@/services/skillApi';
import { db } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import { getToolFunctions } from '@/services/toolApi';
import { getKnowledgeSources } from '@/services/knowledgeApi';
import { getAgentPrompts } from '@/services/agentPromptApi';
import { getMCPServers } from '@/services/mcpApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { createFormSubmitHandler, type TabFieldMapping } from '@/utils/formValidation';
import type { SkillDoc, SkillTool, SkillKnowledge, SkillPrompt, SkillMcpServer } from '@/types/skill.types';
import type { AgentToolFunctionRef } from '@/types/agent.types';
import type { KnowledgeSourceDoc } from '@/types/knowledge.types';
import type { AgentPromptDoc } from '@/services/agentPromptApi';
import type { MCPServerDoc } from '@/services/mcpApi';

const skillFormSchema = z.object({
  skill_name: z.string().min(1, 'Skill name is required'),
  title: z.string().min(1, 'Title is required'),
  description: z.string().optional(),
  skill_category: z.string().optional(),
  version: z.string().optional(),
  author: z.string().optional(),
  source_type: z.enum(['Local', 'Git', 'Common Destination', 'App Provided']).default('Local'),
  source_url: z.string().optional(),
  source_path: z.string().optional(),
  source_ref: z.string().optional(),
  provider_app: z.string().optional(),
  status: z.enum(['Draft', 'Active', 'Error', 'Disabled']).default('Active'),
  instructions: z.string().optional(),
  auto_load: z.boolean().default(true),
});

type SkillFormValues = z.infer<typeof skillFormSchema>;

type CategoryOption = { value: string; label: string };

function normalizeFlag(value: boolean | number | undefined): 0 | 1 {
  return value === true || value === 1 ? 1 : 0;
}

function mapDocToFormValues(doc: Partial<SkillDoc>): SkillFormValues {
  return {
    skill_name: doc.skill_name || '',
    title: doc.title || '',
    description: doc.description || '',
    skill_category: doc.skill_category || '',
    version: doc.version || '',
    author: doc.author || '',
    source_type: doc.source_type || 'Local',
    source_url: doc.source_url || '',
    source_path: doc.source_path || '',
    source_ref: doc.source_ref || '',
    provider_app: doc.provider_app || '',
    status: doc.status || 'Active',
    instructions: doc.instructions || '',
    auto_load: doc.auto_load === 1,
  };
}

function mapFormToPayload(
  values: SkillFormValues,
  tools: SkillTool[],
  knowledge: SkillKnowledge[],
  prompts: SkillPrompt[],
  mcpServers: SkillMcpServer[]
): Partial<SkillDoc> {
  return {
    skill_name: values.skill_name,
    title: values.title,
    description: values.description || '',
    skill_category: values.skill_category || undefined,
    version: values.version || undefined,
    author: values.author || undefined,
    source_type: values.source_type,
    source_url: values.source_url || undefined,
    source_path: values.source_path || undefined,
    source_ref: values.source_ref || undefined,
    provider_app: values.provider_app || undefined,
    status: values.status,
    instructions: values.instructions || undefined,
    auto_load: normalizeFlag(values.auto_load),
    skill_tools: tools.map((t) => ({
      ...(t.name ? { name: t.name } : {}),
      tool: t.tool,
      description: t.description || undefined,
      required: normalizeFlag(t.required),
    })),
    skill_knowledge: knowledge.map((k) => ({
      ...(k.name ? { name: k.name } : {}),
      knowledge_source: k.knowledge_source,
      mode: k.mode,
      max_chunks: k.max_chunks ?? 5,
      token_budget: k.token_budget ?? 2000,
    })),
    skill_prompts: prompts.map((p) => ({
      ...(p.name ? { name: p.name } : {}),
      prompt: p.prompt,
      usage: p.usage,
    })),
    skill_mcp_servers: mcpServers.map((s) => ({
      ...(s.name ? { name: s.name } : {}),
      mcp_server: s.mcp_server,
      enabled: normalizeFlag(s.enabled),
    })),
  };
}

export function SkillFormPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const isNew = id === 'new';

  const tabConfig = useMemo(
    () => ({
      general: {
        label: 'General',
        fields: [
          'skill_name',
          'title',
          'description',
          'skill_category',
          'version',
          'author',
          'source_type',
          'source_url',
          'source_path',
          'source_ref',
          'provider_app',
          'status',
          'instructions',
          'auto_load',
        ],
        default: true,
      },
      tools: { label: 'Tools', fields: [], default: false },
      knowledge: { label: 'Knowledge', fields: [], default: false },
      prompts: { label: 'Prompts', fields: [], default: false },
      mcp: { label: 'MCP', fields: [], default: false },
    }),
    []
  );

  const validTabs = useMemo(() => Object.keys(tabConfig), [tabConfig]);
  const defaultTab = useMemo(
    () => Object.entries(tabConfig).find(([, config]) => config.default)?.[0] || validTabs[0],
    [tabConfig, validTabs]
  );
  const tabFieldMapping: TabFieldMapping = useMemo(
    () => Object.fromEntries(Object.entries(tabConfig).map(([key, config]) => [key, [...config.fields]])),
    [tabConfig]
  );
  const tabLabels = useMemo(
    () => Object.fromEntries(Object.entries(tabConfig).map(([key, config]) => [key, config.label])),
    [tabConfig]
  );

  const [activeTab, setActiveTab] = useState<string>(() => {
    const hashFromUrl = window.location.hash.slice(1);
    return hashFromUrl && validTabs.includes(hashFromUrl) ? hashFromUrl : defaultTab;
  });

  useEffect(() => {
    const handleHashChange = () => {
      const hashFromUrl = window.location.hash.slice(1);
      const tab = hashFromUrl && validTabs.includes(hashFromUrl) ? hashFromUrl : defaultTab;
      setActiveTab(tab);
    };
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, [defaultTab, validTabs]);

  const handleTabChange = (value: string) => {
    setActiveTab(value);
    if (value === defaultTab) {
      window.history.replaceState(null, '', window.location.pathname);
    } else {
      window.location.hash = value;
    }
  };

  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);
  const [categories, setCategories] = useState<CategoryOption[]>([]);

  const [tools, setTools] = useState<SkillTool[]>([]);
  const [initialTools, setInitialTools] = useState<SkillTool[]>([]);
  const [knowledge, setKnowledge] = useState<SkillKnowledge[]>([]);
  const [initialKnowledge, setInitialKnowledge] = useState<SkillKnowledge[]>([]);
  const [prompts, setPrompts] = useState<SkillPrompt[]>([]);
  const [initialPrompts, setInitialPrompts] = useState<SkillPrompt[]>([]);
  const [mcpServers, setMcpServers] = useState<SkillMcpServer[]>([]);
  const [initialMcpServers, setInitialMcpServers] = useState<SkillMcpServer[]>([]);

  const [toolOptions, setToolOptions] = useState<AgentToolFunctionRef[]>([]);
  const [knowledgeOptions, setKnowledgeOptions] = useState<KnowledgeSourceDoc[]>([]);
  const [promptOptions, setPromptOptions] = useState<AgentPromptDoc[]>([]);
  const [mcpOptions, setMcpOptions] = useState<MCPServerDoc[]>([]);

  const form = useForm<SkillFormValues>({
    resolver: zodResolver(skillFormSchema),
    defaultValues: mapDocToFormValues({}),
  });

  const watchStatus = form.watch('status');
  const isDirty = form.formState.isDirty;

  const childTablesChanged = useMemo(() => {
    if (isNew) {
      return tools.length > 0 || knowledge.length > 0 || prompts.length > 0 || mcpServers.length > 0;
    }
    const arraysEqual = (a: unknown[], b: unknown[]) => JSON.stringify(a) === JSON.stringify(b);
    return (
      !arraysEqual(tools, initialTools) ||
      !arraysEqual(knowledge, initialKnowledge) ||
      !arraysEqual(prompts, initialPrompts) ||
      !arraysEqual(mcpServers, initialMcpServers)
    );
  }, [tools, initialTools, knowledge, initialKnowledge, prompts, initialPrompts, mcpServers, initialMcpServers, isNew]);

  const showSaveButton = isNew || isDirty || childTablesChanged;

  useEffect(() => {
    Promise.all([
      getToolFunctions(),
      getKnowledgeSources(),
      getAgentPrompts(),
      getMCPServers(),
      db.getDocList(doctype['Skill Category'], {
        fields: ['name', 'category_name'],
        limit: 1000,
      }),
    ])
      .then(([toolsData, ksData, promptData, mcpData, categoryData]) => {
        setToolOptions((toolsData as AgentToolFunctionRef[]) || []);
        setKnowledgeOptions(((ksData as { items: KnowledgeSourceDoc[] }).items) || []);
        setPromptOptions((promptData as AgentPromptDoc[]) || []);
        setMcpOptions((mcpData as MCPServerDoc[]) || []);
        setCategories(
          (categoryData as Array<{ name: string; category_name?: string }>).map((c) => ({
            value: c.name,
            label: c.category_name || c.name,
          }))
        );
      })
      .catch((error) => {
        console.error('Error loading skill options:', error);
        toast.error('Failed to load some skill options');
      });
  }, []);

  const loadSkill = useCallback(
    async (name: string) => {
      try {
        const doc = await getSkill(name);
        form.reset(mapDocToFormValues(doc));
        setTools(doc.skill_tools || []);
        setInitialTools(doc.skill_tools || []);
        setKnowledge(doc.skill_knowledge || []);
        setInitialKnowledge(doc.skill_knowledge || []);
        setPrompts(doc.skill_prompts || []);
        setInitialPrompts(doc.skill_prompts || []);
        setMcpServers(doc.skill_mcp_servers || []);
        setInitialMcpServers(doc.skill_mcp_servers || []);
      } catch (error) {
        console.error('Error loading skill:', error);
        toast.error(getFrappeErrorMessage(error) || 'Failed to load skill');
      } finally {
        setLoading(false);
      }
    },
    [form]
  );

  useEffect(() => {
    if (id && !isNew) {
      loadSkill(id);
    } else {
      setLoading(false);
    }
  }, [id, isNew, loadSkill]);

  const onSubmit = useCallback(
    async (values: SkillFormValues) => {
      setSaving(true);
      try {
        const payload = mapFormToPayload(values, tools, knowledge, prompts, mcpServers);
        if (isNew) {
          const created = await createSkill(payload);
          toast.success('Skill created');
          navigate(`/skills/${created.name}`);
        } else if (id) {
          const updated = await updateSkill(id, payload);
          toast.success('Skill updated');
          form.reset(mapDocToFormValues(updated));
          setInitialTools(updated.skill_tools || []);
          setInitialKnowledge(updated.skill_knowledge || []);
          setInitialPrompts(updated.skill_prompts || []);
          setInitialMcpServers(updated.skill_mcp_servers || []);
        }
      } catch (error) {
        console.error('Error saving skill:', error);
        toast.error(getFrappeErrorMessage(error) || 'Failed to save skill');
      } finally {
        setSaving(false);
      }
    },
    [tools, knowledge, prompts, mcpServers, id, isNew, navigate, form]
  );

  const handleFormSubmit = useMemo(
    () => createFormSubmitHandler(form, activeTab, tabFieldMapping, tabLabels, onSubmit),
    [form, activeTab, tabFieldMapping, tabLabels, onSubmit]
  );

  const handleDelete = async () => {
    if (isNew || !id) return;
    if (!window.confirm('Delete this skill?')) return;
    try {
      await import('@/services/skillApi').then((m) => m.deleteSkill(id));
      toast.success('Skill deleted');
      navigate('/skills');
    } catch (error) {
      toast.error(getFrappeErrorMessage(error) || 'Failed to delete skill');
    }
  };

  const addTool = (toolName: string) => {
    if (!toolName || tools.some((t) => t.tool === toolName)) return;
    const tool = toolOptions.find((t) => t.name === toolName);
    setTools([...tools, { tool: toolName, tool_name: tool?.tool_name, description: tool?.description }]);
  };

  const removeTool = (index: number) => setTools(tools.filter((_, i) => i !== index));

  const addKnowledge = (ksName: string) => {
    if (!ksName || knowledge.some((k) => k.knowledge_source === ksName)) return;
    const ks = knowledgeOptions.find((k) => k.name === ksName);
    setKnowledge([
      ...knowledge,
      { knowledge_source: ksName, source_name: ks?.source_name, mode: 'Mandatory', max_chunks: 5, token_budget: 2000 },
    ]);
  };

  const updateKnowledge = (index: number, patch: Partial<SkillKnowledge>) => {
    setKnowledge(knowledge.map((k, i) => (i === index ? { ...k, ...patch } : k)));
  };

  const removeKnowledge = (index: number) => setKnowledge(knowledge.filter((_, i) => i !== index));

  const addPrompt = (promptName: string) => {
    if (!promptName || prompts.some((p) => p.prompt === promptName)) return;
    const prompt = promptOptions.find((p) => p.name === promptName);
    setPrompts([...prompts, { prompt: promptName, title: prompt?.title, usage: 'System' }]);
  };

  const updatePrompt = (index: number, patch: Partial<SkillPrompt>) => {
    setPrompts(prompts.map((p, i) => (i === index ? { ...p, ...patch } : p)));
  };

  const removePrompt = (index: number) => setPrompts(prompts.filter((_, i) => i !== index));

  const addMcpServer = (serverName: string) => {
    if (!serverName || mcpServers.some((s) => s.mcp_server === serverName)) return;
    const server = mcpOptions.find((s) => s.name === serverName);
    setMcpServers([...mcpServers, { mcp_server: serverName, server_name: server?.server_name, enabled: true }]);
  };

  const removeMcpServer = (index: number) => setMcpServers(mcpServers.filter((_, i) => i !== index));

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-muted-foreground">Loading skill...</div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto">
      <div className="p-6 space-y-6 max-w-6xl mx-auto">
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div className="flex items-center gap-3 flex-wrap">
            <Sparkles className="w-6 h-6 text-muted-foreground" />
            <div>
              <h1 className="text-2xl font-bold">{isNew ? 'New Skill' : form.watch('title') || 'Skill'}</h1>
              <p className="text-sm text-muted-foreground">{isNew ? 'Create a reusable skill bundle' : form.watch('skill_name')}</p>
            </div>
            <Badge variant={watchStatus === 'Active' ? 'default' : 'secondary'}>{watchStatus}</Badge>
          </div>
          <div className="flex items-center gap-2">
            {showSaveButton && (
              <Button size="sm" onClick={handleFormSubmit} disabled={saving}>
                <Save className="w-4 h-4 mr-2" />
                {saving ? (isNew ? 'Creating...' : 'Saving...') : isNew ? 'Create' : 'Save'}
              </Button>
            )}
            {!isNew && (
              <Button variant="outline" size="sm" onClick={() => exportSkillAsHuf(form.getValues('skill_name'))}>
                <Download className="w-4 h-4 mr-2" />
                Download .huf
              </Button>
            )}
            {!isNew && (
              <Button variant="outline" size="sm" onClick={handleDelete}>
                <Trash2 className="w-4 h-4 mr-2" />
                Delete
              </Button>
            )}
          </div>
        </div>

        <Form {...form}>
          <form onSubmit={handleFormSubmit} className="space-y-6">
            <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">
              <TabsList className="flex h-auto w-full justify-start overflow-x-auto overflow-y-hidden p-1">
                {Object.entries(tabConfig).map(([tabKey, config]) => (
                  <TabsTrigger key={tabKey} value={tabKey} className="flex-1 shrink-0">
                    {config.label}
                  </TabsTrigger>
                ))}
              </TabsList>

              <TabsContent value="general" className="space-y-4">
                <Card>
                  <CardHeader>
                    <CardTitle>General</CardTitle>
                    <CardDescription>Basic skill configuration</CardDescription>
                  </CardHeader>
                  <CardContent className="grid gap-4 sm:grid-cols-2">
                    <FormField
                      control={form.control}
                      name="skill_name"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Skill Name</FormLabel>
                          <FormControl>
                            <Input placeholder="my-skill" {...field} disabled={!isNew} />
                          </FormControl>
                          <FormDescription>Unique machine identifier</FormDescription>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="title"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Title</FormLabel>
                          <FormControl>
                            <Input placeholder="My Skill" {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="skill_category"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Category</FormLabel>
                          <FormControl>
                            <Combobox
                              options={categories}
                              value={field.value || ''}
                              onValueChange={field.onChange}
                              placeholder="Select category..."
                              searchPlaceholder="Search categories..."
                              emptyText="No categories found"
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="status"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Status</FormLabel>
                          <Select onValueChange={field.onChange} value={field.value}>
                            <FormControl>
                              <SelectTrigger>
                                <SelectValue placeholder="Select status" />
                              </SelectTrigger>
                            </FormControl>
                            <SelectContent>
                              <SelectItem value="Draft">Draft</SelectItem>
                              <SelectItem value="Active">Active</SelectItem>
                              <SelectItem value="Error">Error</SelectItem>
                              <SelectItem value="Disabled">Disabled</SelectItem>
                            </SelectContent>
                          </Select>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="version"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Version</FormLabel>
                          <FormControl>
                            <Input placeholder="1.0.0" {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="author"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Author</FormLabel>
                          <FormControl>
                            <Input placeholder="Author or organization" {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="source_type"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Source Type</FormLabel>
                          <Select onValueChange={field.onChange} value={field.value}>
                            <FormControl>
                              <SelectTrigger>
                                <SelectValue placeholder="Select source type" />
                              </SelectTrigger>
                            </FormControl>
                            <SelectContent>
                              <SelectItem value="Local">Local</SelectItem>
                              <SelectItem value="Git">Git</SelectItem>
                              <SelectItem value="Common Destination">Common Destination</SelectItem>
                              <SelectItem value="App Provided">App Provided</SelectItem>
                            </SelectContent>
                          </Select>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="provider_app"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Provider App</FormLabel>
                          <FormControl>
                            <Input placeholder="huf" {...field} />
                          </FormControl>
                          <FormDescription>Required for App Provided skills</FormDescription>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="source_url"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Source URL</FormLabel>
                          <FormControl>
                            <Input placeholder="https://github.com/org/repo" {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="source_path"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Source Path</FormLabel>
                          <FormControl>
                            <Input placeholder="skills" {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="source_ref"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Source Ref</FormLabel>
                          <FormControl>
                            <Input placeholder="main" {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="auto_load"
                      render={({ field }) => (
                        <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4 sm:col-span-2">
                          <div className="space-y-0.5">
                            <FormLabel className="text-base">Auto Load</FormLabel>
                            <FormDescription>Load this skill automatically when attached</FormDescription>
                          </div>
                          <FormControl>
                            <Switch checked={field.value} onCheckedChange={field.onChange} />
                          </FormControl>
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="description"
                      render={({ field }) => (
                        <FormItem className="sm:col-span-2">
                          <FormLabel>Description</FormLabel>
                          <FormControl>
                            <Textarea
                              placeholder="Short description shown in the UI and to agents"
                              className="min-h-[80px] resize-y"
                              {...field}
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="instructions"
                      render={({ field }) => (
                        <FormItem className="sm:col-span-2">
                          <FormLabel>Instructions</FormLabel>
                          <FormControl>
                            <Textarea
                              placeholder="System prompt text injected when this skill is loaded"
                              className="min-h-[160px] resize-y"
                              {...field}
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </CardContent>
                </Card>
              </TabsContent>

              <TabsContent value="tools" className="space-y-4">
                <ChildTableCard
                  title="Tools"
                  description="Agent Tool Functions included in this skill"
                  icon={Server}
                  emptyText="No tools linked yet."
                  addLabel="Add Tool"
                  options={toolOptions.map((t) => ({ value: t.name, label: t.tool_name || t.name, subtitle: t.description }))}
                  onAdd={addTool}
                >
                  {tools.map((tool, index) => (
                    <div
                      key={tool.name || `tool-${index}`}
                      className="flex items-start justify-between gap-3 rounded-lg border p-4 hover:bg-muted/50"
                    >
                      <div className="min-w-0 space-y-1">
                        <p className="font-medium text-sm">{tool.tool_name || tool.tool}</p>
                        {tool.description && <p className="text-xs text-muted-foreground line-clamp-2">{tool.description}</p>}
                      </div>
                      <Button variant="ghost" size="sm" onClick={() => removeTool(index)} type="button">
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </div>
                  ))}
                </ChildTableCard>
              </TabsContent>

              <TabsContent value="knowledge" className="space-y-4">
                <ChildTableCard
                  title="Knowledge"
                  description="Knowledge sources attached to this skill"
                  icon={BookOpen}
                  emptyText="No knowledge sources linked yet."
                  addLabel="Add Knowledge"
                  options={knowledgeOptions.map((k) => ({ value: k.name, label: k.source_name || k.name, subtitle: k.description || '' }))}
                  onAdd={addKnowledge}
                >
                  {knowledge.map((ks, index) => (
                    <div
                      key={ks.name || `ks-${index}`}
                      className="flex flex-col gap-3 rounded-lg border p-4 hover:bg-muted/50"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="min-w-0">
                          <p className="font-medium text-sm">{ks.source_name || ks.knowledge_source}</p>
                          <p className="text-xs text-muted-foreground">{ks.knowledge_source}</p>
                        </div>
                        <Button variant="ghost" size="sm" onClick={() => removeKnowledge(index)} type="button">
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      </div>
                      <div className="grid grid-cols-3 gap-3">
                        <Select value={ks.mode} onValueChange={(v) => updateKnowledge(index, { mode: v as SkillKnowledge['mode'] })}>
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="Mandatory">Mandatory</SelectItem>
                            <SelectItem value="Optional">Optional</SelectItem>
                          </SelectContent>
                        </Select>
                        <Input
                          type="number"
                          placeholder="Max chunks"
                          value={ks.max_chunks ?? 5}
                          onChange={(e) => updateKnowledge(index, { max_chunks: Number(e.target.value) })}
                        />
                        <Input
                          type="number"
                          placeholder="Token budget"
                          value={ks.token_budget ?? 2000}
                          onChange={(e) => updateKnowledge(index, { token_budget: Number(e.target.value) })}
                        />
                      </div>
                    </div>
                  ))}
                </ChildTableCard>
              </TabsContent>

              <TabsContent value="prompts" className="space-y-4">
                <ChildTableCard
                  title="Prompts"
                  description="Agent Prompt templates included in this skill"
                  icon={ScrollText}
                  emptyText="No prompts linked yet."
                  addLabel="Add Prompt"
                  options={promptOptions.map((p) => ({ value: p.name, label: p.title || p.name, subtitle: p.description || '' }))}
                  onAdd={addPrompt}
                >
                  {prompts.map((prompt, index) => (
                    <div
                      key={prompt.name || `prompt-${index}`}
                      className="flex flex-col gap-3 rounded-lg border p-4 hover:bg-muted/50"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="min-w-0">
                          <p className="font-medium text-sm">{prompt.title || prompt.prompt}</p>
                          <p className="text-xs text-muted-foreground">{prompt.prompt}</p>
                        </div>
                        <Button variant="ghost" size="sm" onClick={() => removePrompt(index)} type="button">
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      </div>
                      <Select value={prompt.usage} onValueChange={(v) => updatePrompt(index, { usage: v as SkillPrompt['usage'] })}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="System">System</SelectItem>
                          <SelectItem value="User">User</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  ))}
                </ChildTableCard>
              </TabsContent>

              <TabsContent value="mcp" className="space-y-4">
                <ChildTableCard
                  title="MCP Servers"
                  description="MCP servers bundled with this skill"
                  icon={Plug}
                  emptyText="No MCP servers linked yet."
                  addLabel="Add MCP Server"
                  options={mcpOptions.map((s) => ({ value: s.name, label: s.server_name || s.name, subtitle: s.description || '' }))}
                  onAdd={addMcpServer}
                >
                  {mcpServers.map((server, index) => (
                    <div
                      key={server.name || `mcp-${index}`}
                      className="flex items-center justify-between gap-3 rounded-lg border p-4 hover:bg-muted/50"
                    >
                      <div className="min-w-0 space-y-1">
                        <p className="font-medium text-sm">{server.server_name || server.mcp_server}</p>
                        {server.mcp_server !== (server.server_name || '') && (
                          <p className="text-xs text-muted-foreground">{server.mcp_server}</p>
                        )}
                      </div>
                      <Button variant="ghost" size="sm" onClick={() => removeMcpServer(index)} type="button">
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </div>
                  ))}
                </ChildTableCard>
              </TabsContent>
            </Tabs>
          </form>
        </Form>
      </div>
    </div>
  );
}

interface ChildTableCardProps {
  title: string;
  description: string;
  icon: React.ElementType;
  emptyText: string;
  addLabel: string;
  options: { value: string; label: string; subtitle?: string }[];
  onAdd: (value: string) => void;
  children: React.ReactNode;
}

function ChildTableCard({ title, description, icon: Icon, emptyText, addLabel, options, onAdd, children }: ChildTableCardProps) {
  const [value, setValue] = useState('');
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Icon className="w-5 h-5" />
              {title}
            </CardTitle>
            <CardDescription>{description}</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-end gap-2">
          <div className="flex-1">
            <Combobox
              options={options}
              value={value}
              onValueChange={setValue}
              placeholder={addLabel}
              searchPlaceholder={`Search ${title.toLowerCase()}...`}
              emptyText={`No ${title.toLowerCase()} found`}
            />
          </div>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => {
              if (value) {
                onAdd(value);
                setValue('');
              }
            }}
            disabled={!value}
          >
            <Plus className="w-4 h-4 mr-2" />
            {addLabel}
          </Button>
        </div>

        {Array.isArray(children) && children.length === 0 ? (
          <div className="text-center py-12 border border-dashed rounded-lg bg-muted/20">
            <p className="text-muted-foreground">{emptyText}</p>
          </div>
        ) : (
          <div className="grid gap-3">{children}</div>
        )}
      </CardContent>
    </Card>
  );
}

export default SkillFormPage;
