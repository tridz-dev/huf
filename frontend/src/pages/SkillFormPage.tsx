import { useResourceAccess } from '@/hooks/permissions/useResourceAccess';
import { useEffect, useMemo, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { toast } from 'sonner';
import { Form } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Trash2, Server, BookOpen, ScrollText, Plug, Save, Sparkles, Download } from 'lucide-react';
import { getSkill, createSkill, updateSkill, exportSkillAsHuf } from '@/services/skillApi';
import { getToolFunctions } from '@/services/toolApi';
import { getKnowledgeSources } from '@/services/knowledgeApi';
import { getAgentPrompts } from '@/services/agentPromptApi';
import { getMCPServers } from '@/services/mcpApi';
import { getCategories, type CategoryDoc } from '@/services/categoryApi';
import { Label } from '@/components/ui/label';
import { ChildTableCard } from '@/components/skills/SkillChildTableCard';
import { SkillGeneralTab } from '@/components/skills/SkillGeneralTab';
import { CategoryModal } from '@/components/category/CategoryModal';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { createFormSubmitHandler, type TabFieldMapping } from '@/utils/formValidation';
import type { SkillTool, SkillKnowledge, SkillPrompt, SkillMcpServer } from '@/types/skill.types';
import {
  skillFormSchema,
  SKILL_ADVANCED_FIELDS,
  mapDocToFormValues,
  mapFormToPayload,
  type SkillFormValues,
} from '@/components/skills/skillFormSchema';
import type { AgentToolFunctionRef } from '@/types/agent.types';
import type { KnowledgeSourceDoc } from '@/types/knowledge.types';
import type { AgentPromptDoc } from '@/services/agentPromptApi';
import type { MCPServerDoc } from '@/services/mcpApi';

export function SkillFormPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const access = useResourceAccess('skill');
  const isNew = id === 'new';

  const tabConfig = useMemo(
    () => ({
      general: {
        label: 'General',
        fields: ['title', 'description', 'skill_category', 'instructions', ...SKILL_ADVANCED_FIELDS],
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
  const [categoryModalOpen, setCategoryModalOpen] = useState(false);
  const [editingCategory, setEditingCategory] = useState<CategoryDoc | null>(null);
  const [selectedCategory, setSelectedCategory] = useState<CategoryDoc | null>(null);
  const [allCategories, setAllCategories] = useState<CategoryDoc[]>([]);

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
      getCategories(undefined, 'skill'),
    ])
      .then(([toolsData, ksData, promptData, mcpData, categoryData]) => {
        setToolOptions((toolsData as AgentToolFunctionRef[]) || []);
        setKnowledgeOptions(((ksData as { items: KnowledgeSourceDoc[] }).items) || []);
        setPromptOptions((promptData as AgentPromptDoc[]) || []);
        setMcpOptions((mcpData as MCPServerDoc[]) || []);
        setAllCategories(categoryData);
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

  useEffect(() => {
    const skillCategoryValue = form.watch('skill_category');
    if (allCategories.length > 0 && skillCategoryValue) {
      const match = allCategories.find((c) => c.name === skillCategoryValue);
      if (match) {
        setSelectedCategory(match);
      }
    }
  }, [allCategories, form]);

  useEffect(() => {
    if (selectedCategory) {
      form.setValue('skill_category', selectedCategory.name, { shouldDirty: false });
    }
  }, [selectedCategory, form]);

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

  const addTools = (names: string[]) =>
    setTools((prev) => {
      const fresh = names.filter((n) => n && !prev.some((t) => t.tool === n));
      return [
        ...prev,
        ...fresh.map((n) => {
          const tool = toolOptions.find((t) => t.name === n);
          return { tool: n, tool_name: tool?.tool_name, description: tool?.description };
        }),
      ];
    });

  const removeTool = (index: number) => setTools(tools.filter((_, i) => i !== index));

  const addKnowledge = (names: string[]) =>
    setKnowledge((prev) => [
      ...prev,
      ...names
        .filter((n) => n && !prev.some((k) => k.knowledge_source === n))
        .map((n) => ({
          knowledge_source: n,
          source_name: knowledgeOptions.find((k) => k.name === n)?.source_name,
          mode: 'Mandatory' as const,
          max_chunks: 5,
          token_budget: 2000,
        })),
    ]);

  const updateKnowledge = (index: number, patch: Partial<SkillKnowledge>) => {
    setKnowledge(knowledge.map((k, i) => (i === index ? { ...k, ...patch } : k)));
  };

  const removeKnowledge = (index: number) => setKnowledge(knowledge.filter((_, i) => i !== index));

  const addPrompts = (names: string[]) =>
    setPrompts((prev) => [
      ...prev,
      ...names
        .filter((n) => n && !prev.some((p) => p.prompt === n))
        .map((n) => ({
          prompt: n,
          title: promptOptions.find((p) => p.name === n)?.title,
          usage: 'System' as const,
        })),
    ]);

  const updatePrompt = (index: number, patch: Partial<SkillPrompt>) => {
    setPrompts(prompts.map((p, i) => (i === index ? { ...p, ...patch } : p)));
  };

  const removePrompt = (index: number) => setPrompts(prompts.filter((_, i) => i !== index));

  const addMcpServers = (names: string[]) =>
    setMcpServers((prev) => [
      ...prev,
      ...names
        .filter((n) => n && !prev.some((s) => s.mcp_server === n))
        .map((n) => ({
          mcp_server: n,
          server_name: mcpOptions.find((s) => s.name === n)?.server_name,
          enabled: true,
        })),
    ]);

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
              <h1 className="font-display text-title text-ink">{isNew ? 'New Skill' : form.watch('title') || 'Skill'}</h1>
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
              <Button variant="outline" size="sm" onClick={() => exportSkillAsHuf(form.getValues('skill_name') || id || '')}>
                <Download className="w-4 h-4 mr-2" />
                Download .huf
              </Button>
            )}
            {!isNew && access.canDelete && (
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
              <TabsList layout="scroll" className="w-full">
                {Object.entries(tabConfig).map(([tabKey, config]) => (
                  <TabsTrigger key={tabKey} value={tabKey} className="shrink-0">
                    {config.label}
                  </TabsTrigger>
                ))}
              </TabsList>

              <TabsContent value="general" className="space-y-4">
                <SkillGeneralTab
                  form={form}
                  selectedCategory={selectedCategory}
                  onAddCategory={() => {
                    setEditingCategory(null);
                    setCategoryModalOpen(true);
                  }}
                  onRemoveCategory={() => setSelectedCategory(null)}
                  onEditCategory={(category) => {
                    setEditingCategory(category);
                    setCategoryModalOpen(true);
                  }}
                />
              </TabsContent>

              <TabsContent value="tools" className="space-y-4">
                <ChildTableCard
                  title="Tools"
                  description="Agent Tool Functions included in this skill"
                  icon={Server}
                  emptyText="No tools linked yet."
                  addLabel="Add Tool"
                  options={toolOptions.map((t) => ({ value: t.name, label: t.tool_name || t.name, subtitle: t.description }))}
                  onAdd={addTools}
                >
                  {tools.map((tool, index) => (
                    <div
                      key={tool.name || `tool-${index}`}
                      className="flex items-start justify-between gap-3 rounded-lg border p-4 hover:bg-muted/50"
                    >
                      <div className="min-w-0 space-y-1">
                        <p className="font-medium text-sm">{tool.tool_name || toolOptions.find((o) => o.name === tool.tool)?.tool_name || tool.tool}</p>
                        {(tool.description || toolOptions.find((o) => o.name === tool.tool)?.description) && (
                          <p className="text-xs text-muted-foreground line-clamp-2">
                            {tool.description || toolOptions.find((o) => o.name === tool.tool)?.description}
                          </p>
                        )}
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
                          <p className="font-medium text-sm">
                            {ks.source_name || knowledgeOptions.find((o) => o.name === ks.knowledge_source)?.source_name || ks.knowledge_source}
                          </p>
                        </div>
                        <Button variant="ghost" size="sm" onClick={() => removeKnowledge(index)} type="button">
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      </div>
                      <div className="grid grid-cols-3 gap-3">
                        <div className="space-y-1.5">
                          <Label>Mode</Label>
                          <Select value={ks.mode} onValueChange={(v) => updateKnowledge(index, { mode: v as SkillKnowledge['mode'] })}>
                            <SelectTrigger>
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="Mandatory">Mandatory</SelectItem>
                              <SelectItem value="Optional">Optional</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                        <div className="space-y-1.5">
                          <Label>Max chunks</Label>
                          <Input
                            type="number"
                            placeholder="e.g. 5"
                            value={ks.max_chunks ?? 5}
                            onChange={(e) => updateKnowledge(index, { max_chunks: Number(e.target.value) })}
                          />
                        </div>
                        <div className="space-y-1.5">
                          <Label>Token budget</Label>
                          <Input
                            type="number"
                            placeholder="e.g. 2000"
                            value={ks.token_budget ?? 2000}
                            onChange={(e) => updateKnowledge(index, { token_budget: Number(e.target.value) })}
                          />
                        </div>
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
                  onAdd={addPrompts}
                >
                  {prompts.map((prompt, index) => (
                    <div
                      key={prompt.name || `prompt-${index}`}
                      className="flex flex-col gap-3 rounded-lg border p-4 hover:bg-muted/50"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="min-w-0">
                          <p className="font-medium text-sm">
                            {prompt.title || promptOptions.find((o) => o.name === prompt.prompt)?.title || prompt.prompt}
                          </p>
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
                  title="MCP servers"
                  description="MCP servers bundled with this skill"
                  icon={Plug}
                  emptyText="No MCP servers linked yet."
                  addLabel="Add MCP Server"
                  options={mcpOptions.map((s) => ({ value: s.name, label: s.server_name || s.name, subtitle: s.description || '' }))}
                  onAdd={addMcpServers}
                >
                  {mcpServers.map((server, index) => (
                    <div
                      key={server.name || `mcp-${index}`}
                      className="flex items-center justify-between gap-3 rounded-lg border p-4 hover:bg-muted/50"
                    >
                      <div className="min-w-0 space-y-1">
                        <p className="font-medium text-sm">
                          {server.server_name || mcpOptions.find((o) => o.name === server.mcp_server)?.server_name || server.mcp_server}
                        </p>
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
          <CategoryModal
            categoryType="skill"
            open={categoryModalOpen}
            onOpenChange={(open) => {
              setCategoryModalOpen(open);
              if (!open) setEditingCategory(null);
            }}
            categories={allCategories}
            selected={selectedCategory}
            onSave={setSelectedCategory}
            refreshCategories={async () => {
              const data = await getCategories(undefined, 'skill');
              setAllCategories(data);
            }}
            editCategory={editingCategory}
            onEditComplete={() => setEditingCategory(null)}
          />
        </Form>
      </div>
    </div>
  );
}

export default SkillFormPage;
