import { useState, useEffect, useMemo } from 'react';
import { Search } from 'lucide-react';
import {
  Dialog,
  DialogDescription,
  DialogTitle,
} from '../ui/dialog';
import {
  DialogScrollContent,
  DialogScrollFooter,
  DialogScrollHeader,
} from '../ui/dialog-scroll';
import { Input } from '../ui/input';
import { Button } from '../ui/button';
import { Combobox } from '../ui/combobox';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../ui/tabs';
import { ToolCard } from './ToolCard';
import { ToolTemplateCard } from './ToolTemplateCard';
import { ToolCreationForm } from './ToolCreationForm';
import { getToolFunctions, getToolTypes, createToolFunction, getAgentsUsingTool } from '@/services/toolApi';
import type { AgentToolFunctionRef, AgentToolType } from '@/types/agent.types';
import type { ToolTemplate, ToolFormData } from '@/types/toolTemplate.types';
import { getToolTypeDisplayLabel } from '@/data/ai';
import { getIntegrationSettings } from '@/services/integrationApi';
import type { IntegrationSettingsDoc } from '@/types/integration.types';
import { getCategoryIcon } from './toolCategoryIcon';
import { formatServiceLabel } from './toolPresentation';
import { toast } from 'sonner';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import toolTemplatesConfig from '@/config/toolTemplates.json';
import { Badge } from '../ui/badge';
import { ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';

const UNCATEGORIZED_GROUP = '__uncategorized__';
const UNCATEGORIZED_LABEL = 'Other Tools';

interface SelectToolsModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  selectedTools: AgentToolFunctionRef[];
  onAddTools: (tools: AgentToolFunctionRef[]) => void;
}

export function SelectToolsModal({
  open,
  onOpenChange,
  selectedTools,
  onAddTools,
}: SelectToolsModalProps) {
  const [allTools, setAllTools] = useState<AgentToolFunctionRef[]>([]);
  const [toolTypes, setToolTypes] = useState<AgentToolType[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [toolTypeFilter, setToolTypeFilter] = useState<string>('all');
  const [selectedToolIds, setSelectedToolIds] = useState<Set<string>>(
    new Set(selectedTools.map((t) => t.name))
  );
  const [toolUsageMap, setToolUsageMap] = useState<Map<string, string[]>>(new Map());
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
  /** Integration Service keys with at least one active Integration Settings. */
  const [connectedServices, setConnectedServices] = useState<Set<string>>(new Set());
  
  // Tab and view state
  const [activeTab, setActiveTab] = useState<'tool-library' | 'create-new'>('tool-library');
  const [createView, setCreateView] = useState<'templates' | 'form'>('templates');
  const [selectedTemplate, setSelectedTemplate] = useState<ToolTemplate | null>(null);
  const [creatingTool, setCreatingTool] = useState(false);
  
  // Load templates from config
  const templates = useMemo(() => toolTemplatesConfig.templates as ToolTemplate[], []);

  // Load tools and tool types when modal opens
  useEffect(() => {
    if (open) {
      setLoading(true);
      Promise.all([
        getToolTypes(),
        getToolFunctions(),
        // Which services actually have credentials configured — lets the
        // picker warn before a tool is attached rather than at run time.
        getIntegrationSettings().catch(() => [] as IntegrationSettingsDoc[]),
      ])
        .then(async ([types, tools, settings]) => {
          setToolTypes(types);
          setAllTools(tools);

          const settingsList = Array.isArray(settings) ? settings : settings.items;
          setConnectedServices(
            new Set(
              settingsList
                .filter((s) => s.is_active && s.service)
                .map((s) => s.service)
            )
          );

          // Load tool usage data
          const usageMap = new Map<string, string[]>();
          await Promise.all(
            tools.map(async (tool) => {
              try {
                const agents = await getAgentsUsingTool(tool.name);
                if (agents.length > 0) {
                  usageMap.set(tool.name, agents);
                }
              } catch (error) {
                console.error(`Error loading usage for tool ${tool.name}:`, error);
              }
            })
          );
          setToolUsageMap(usageMap);
          
          setLoading(false);
        })
        .catch((error) => {
          console.error('Error loading tools/types:', error);
          const errorMessage = getFrappeErrorMessage(error);
          toast.error(errorMessage || 'Failed to load tools');
          setLoading(false);
        });
      
      // Reset filters and selection when opening
      setSearchQuery('');
      setToolTypeFilter('all');
      setSelectedToolIds(new Set(selectedTools.map((t) => t.name)));
      setActiveTab('tool-library');
      setCreateView('templates');
      setSelectedTemplate(null);
      setExpandedGroups(new Set());
    }
  }, [open, selectedTools]);

  // Update selected tool IDs when selectedTools prop changes
  useEffect(() => {
    if (open) {
      setSelectedToolIds(new Set(selectedTools.map((t) => t.name)));
    }
  }, [selectedTools, open]);

  // Create a map of tool_type name -> AgentToolType for quick lookup
  const toolTypesMap = useMemo(() => {
    const map = new Map<string, AgentToolType>();
    toolTypes.forEach((type) => {
      map.set(type.name, type);
    });
    return map;
  }, [toolTypes]);

  // Prepare tool type options for Combobox
  const toolTypeOptions = useMemo(() => {
    const options = [
      { value: 'all', label: 'All tool types' },
      ...toolTypes.map((type) => ({
        value: type.name,
        label: getToolTypeDisplayLabel(type.name1 || type.name),
      })),
    ];
    return options;
  }, [toolTypes]);

  // Filter tools based on search and tool_type filter
  const filteredTools = useMemo(() => {
    return allTools.filter((tool) => {
      // Search filter - search by name (which is the tool_name) and description
      const matchesSearch =
        searchQuery === '' ||
        (tool.tool_name || tool.name).toLowerCase().includes(searchQuery.toLowerCase()) ||
        tool.description?.toLowerCase().includes(searchQuery.toLowerCase());

      // Tool type filter (using tool_type link field)
      const matchesToolType = toolTypeFilter === 'all' || tool.tool_type === toolTypeFilter;

      return matchesSearch && matchesToolType;
    });
  }, [allTools, searchQuery, toolTypeFilter]);

  // Two sections, because they answer different questions.
  //
  // "From your connected apps" groups by `service` — the Integration Service a
  // tool needs credentials for. That is the same object the /integrations page
  // manages, so connecting Slack there now visibly unlocks the Slack tools
  // here, and a tool whose account is missing can say so up front.
  //
  // "Built-in" is everything with no service: platform capabilities that always
  // work (Memory, Builder, Documents, ...). Those group by Agent Tool Type.
  //
  // Neither section uses the `types` field: it records the implementation
  // mechanism and is "App Provided" for ~90% of tools.
  const { serviceGroups, builtinGroups } = useMemo(() => {
    const byService = new Map<string, AgentToolFunctionRef[]>();
    const byToolType = new Map<string, { label: string; tools: AgentToolFunctionRef[] }>();

    filteredTools.forEach((tool) => {
      if (tool.service) {
        const list = byService.get(tool.service) ?? [];
        list.push(tool);
        byService.set(tool.service, list);
        return;
      }
      const key = tool.tool_type || UNCATEGORIZED_GROUP;
      const rawLabel = tool.tool_type
        ? toolTypesMap.get(tool.tool_type)?.name1 || tool.tool_type
        : UNCATEGORIZED_LABEL;
      const entry = byToolType.get(key) ?? {
        label: getToolTypeDisplayLabel(rawLabel),
        tools: [],
      };
      entry.tools.push(tool);
      byToolType.set(key, entry);
    });

    return {
      serviceGroups: Array.from(byService.entries())
        .map(([service, tools]) => ({
          key: `service:${service}`,
          label: formatServiceLabel(service),
          tools,
          connected: connectedServices.has(service),
        }))
        // Connected apps first — those are usable right now.
        .sort((a, b) =>
          a.connected !== b.connected
            ? Number(b.connected) - Number(a.connected)
            : b.tools.length - a.tools.length
        ),
      builtinGroups: Array.from(byToolType.entries())
        .map(([key, { label, tools }]) => ({ key, label, tools, connected: true }))
        .sort((a, b) => {
          if (a.key === UNCATEGORIZED_GROUP) return 1;
          if (b.key === UNCATEGORIZED_GROUP) return -1;
          return b.tools.length - a.tools.length;
        }),
    };
  }, [filteredTools, toolTypesMap, connectedServices]);

  // Collapsed by default so the modal opens as a short list of categories
  // rather than a scroll of 130+ rows. An active search expands everything,
  // since a filtered result set is the thing the user wants to see at once.
  const isSearching = searchQuery.trim() !== '' || toolTypeFilter !== 'all';
  const toggleGroup = (key: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const renderGroup = ({
    key,
    label,
    tools,
    connected,
  }: {
    key: string;
    label: string;
    tools: AgentToolFunctionRef[];
    connected: boolean;
  }) => {
    const Icon = getCategoryIcon(label);
    const expanded = isSearching || expandedGroups.has(key);
    const selectedHere = tools.filter((t) => selectedToolIds.has(t.name)).length;
    const isService = key.startsWith('service:');

    return (
      <div key={key} className="mb-2 last:mb-0">
        <button
          type="button"
          onClick={() => toggleGroup(key)}
          aria-expanded={expanded}
          className={cn(
            'flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left transition-colors',
            'hover:bg-paper-deep focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'
          )}
        >
          <ChevronRight
            className={cn(
              'h-4 w-4 shrink-0 text-steel-soft transition-transform',
              expanded && 'rotate-90'
            )}
            aria-hidden="true"
          />
          <Icon className="h-4 w-4 shrink-0 text-steel-soft" aria-hidden="true" />
          <span className="text-sm font-medium text-foreground">{label}</span>
          <span className="text-xs text-steel-soft">{tools.length}</span>
          {isService && !connected && (
            <Badge variant="outline" className="shrink-0 text-[10px] font-normal">
              Needs setup
            </Badge>
          )}
          {selectedHere > 0 && (
            <Badge variant="secondary" className="ml-auto shrink-0 text-[10px]">
              {selectedHere} selected
            </Badge>
          )}
        </button>
        {expanded && (
          <div className="mt-1 space-y-2 pl-6">
            {isService && !connected && (
              <p className="pb-1 text-xs text-steel-soft">
                These tools need a connected {label} account.{' '}
                <a href="/huf/integrations" className="underline hover:text-foreground">
                  Connect {label}
                </a>{' '}
                to use them.
              </p>
            )}
            {tools.map((tool) => (
              <ToolCard
                key={tool.name}
                tool={tool}
                selected={selectedToolIds.has(tool.name)}
                onSelect={handleToolToggle}
                usedByAgents={toolUsageMap.get(tool.name) || []}
              />
            ))}
          </div>
        )}
      </div>
    );
  };

  const handleToolToggle = (tool: AgentToolFunctionRef) => {
    const newSelectedIds = new Set(selectedToolIds);
    if (newSelectedIds.has(tool.name)) {
      newSelectedIds.delete(tool.name);
    } else {
      newSelectedIds.add(tool.name);
    }
    setSelectedToolIds(newSelectedIds);
  };

  const handleAdd = () => {
    const toolsToAdd = filteredTools.filter((tool) =>
      selectedToolIds.has(tool.name)
    );
    
    // Only add tools that aren't already selected
    const newTools = toolsToAdd.filter(
      (tool) => !selectedTools.some((st) => st.name === tool.name)
    );

    // Always close the modal
    onOpenChange(false);

    // Only show success message if new tools were added
    if (newTools.length > 0) {
      onAddTools(newTools);
      toast.success(`Added ${newTools.length} tool${newTools.length > 1 ? 's' : ''}`);
    }
  };

  const selectedCount = filteredTools.filter((tool) =>
    selectedToolIds.has(tool.name)
  ).length;

  const handleTemplateClick = (template: ToolTemplate) => {
    setSelectedTemplate(template);
    setCreateView('form');
  };

  const handleFormBack = () => {
    setCreateView('templates');
    setSelectedTemplate(null);
  };

  const handleFormSubmit = async (data: ToolFormData) => {
    if (!selectedTemplate) return;
    setCreatingTool(true);
    try {
      const newTool = await createToolFunction({
        tool_name: data.tool_name,
        tool_type: data.tool_type,
        types: data.types,
        description: data.description,
        reference_doctype: data.reference_doctype,
        agent: data.agent,
        function_path: data.function_path,
        function_name: data.function_name,
        pass_parameters_as_json: data.pass_parameters_as_json,
        provider_app: data.provider_app,
        base_url: data.base_url,
        required_permission: data.required_permission,
        is_read_only: data.is_read_only,
        allowed_for_guest: data.allowed_for_guest,
        parameters: data.parameters,
        http_headers: data.http_headers,
      });
      
      // Refresh the tools list to include the new tool
      const updatedTools = await getToolFunctions();
      setAllTools(updatedTools || []);
      
      if (data.auto_add_to_agent !== false) {
        // Auto-select the newly created tool
        const newSelectedIds = new Set(selectedToolIds);
        newSelectedIds.add(newTool.name);
        setSelectedToolIds(newSelectedIds);

        // Add the created tool to the agent
        onAddTools([newTool]);

        toast.success('Tool created and added successfully!');
      } else {
        toast.success('Tool created successfully!');
      }

      // Switch back to Tool Library tab and reset form view
      setActiveTab('tool-library');
      setCreateView('templates');
      setSelectedTemplate(null);
    } catch (error) {
      console.error('Error creating tool:', error);
      const errorMessage = getFrappeErrorMessage(error);
      toast.error(errorMessage || 'Failed to create tool');
    } finally {
      setCreatingTool(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogScrollContent className="sm:max-w-5xl">
        <DialogScrollHeader>
          <DialogTitle>Add tool</DialogTitle>
        </DialogScrollHeader>

        {/* Tabs */}
        <Tabs 
          value={activeTab} 
          onValueChange={(value) => setActiveTab(value as 'tool-library' | 'create-new')} 
          className="flex min-h-0 flex-1 flex-col overflow-hidden px-6"
        >
          <TabsList layout="grid" cols={2} className="flex-shrink-0">
            <TabsTrigger value="tool-library">Tool library</TabsTrigger>
            <TabsTrigger value="create-new">Create new</TabsTrigger>
          </TabsList>

          {/* Tool Library Tab */}
          <TabsContent 
            value="tool-library" 
            className="mt-4 data-[state=active]:flex data-[state=active]:flex-col data-[state=active]:flex-1 data-[state=active]:min-h-0 data-[state=active]:overflow-hidden"
          >
            <div className="pb-2 flex items-center justify-between gap-2 flex-shrink-0">
              <DialogDescription>
                Choose tools to add to this agent. Select multiple tools at once.
              </DialogDescription>
              <Badge variant="outline" className="shrink-0">
                {selectedCount} selected
              </Badge>
            </div>

            {/* Filters */}
            <div className="flex flex-col gap-3 mb-4 flex-shrink-0">
              {/* Search */}
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-steel-soft" />
                <Input
                  placeholder="Search tools by name or description..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-9"
                />
              </div>

              {/* Tool Type Filter - Combobox */}
              <Combobox
                options={toolTypeOptions}
                value={toolTypeFilter}
                onValueChange={(value) => setToolTypeFilter(value || 'all')}
                placeholder="Select tool type..."
                searchPlaceholder="Search tool types..."
                emptyText="No tool type found."
              />
            </div>

            {/* Tool List */}
            <div className="flex-1 overflow-y-auto min-h-0 space-y-2 pb-2">
              {loading ? (
                <div className="flex items-center justify-center py-12">
                  <div className="font-body text-steel-soft">Loading tools...</div>
                </div>
              ) : filteredTools.length === 0 ? (
                <div className="flex items-center justify-center py-12">
                  <div className="text-steel">
                    {searchQuery || toolTypeFilter !== 'all'
                      ? 'No tools match your filters'
                      : 'No tools available'}
                  </div>
                </div>
              ) : (
                <>
                  {serviceGroups.length > 0 && (
                    <section>
                      <h3 className="px-2 pb-1 text-xs font-semibold uppercase tracking-wide text-steel">
                        From your connected apps
                      </h3>
                      {serviceGroups.map(renderGroup)}
                    </section>
                  )}
                  {builtinGroups.length > 0 && (
                    <section className={cn(serviceGroups.length > 0 && 'mt-4 border-t border-line pt-4')}>
                      <h3 className="px-2 pb-1 text-xs font-semibold uppercase tracking-wide text-steel">
                        Built-in
                      </h3>
                      <p className="px-2 pb-2 text-xs text-steel-soft">
                        Always available — no account to connect.
                      </p>
                      {builtinGroups.map(renderGroup)}
                    </section>
                  )}
                </>
              )}
            </div>
          </TabsContent>

          {/* Create New Tab */}
          <TabsContent 
            value="create-new" 
            className="mt-4 data-[state=active]:flex data-[state=active]:flex-col data-[state=active]:flex-1 data-[state=active]:min-h-0 data-[state=active]:overflow-y-auto"
          >
            {createView === 'templates' ? (
              <div className="grid grid-cols-2 gap-4 max-w-4xl mx-auto pb-4">
                {templates.map((template) => (
                  <ToolTemplateCard
                    key={template.id}
                    template={template}
                    onClick={() => handleTemplateClick(template)}
                  />
                ))}
              </div>
            ) : selectedTemplate ? (
              <div className="pb-4">
                <ToolCreationForm
                  template={selectedTemplate}
                  toolTypes={toolTypes}
                  onSubmit={handleFormSubmit}
                  onBack={handleFormBack}
                  loading={creatingTool}
                />
              </div>
            ) : null}
          </TabsContent>
        </Tabs>

        {activeTab === 'tool-library' && (
          <DialogScrollFooter className="items-center justify-between sm:justify-between">
            <div className="text-sm text-steel">
              {selectedCount > 0 ? (
                <>
                  {selectedCount} tool{selectedCount > 1 ? 's' : ''} selected
                  {selectedCount !== filteredTools.length && (
                    <> • {filteredTools.length} total</>
                  )}
                </>
              ) : (
                <>{filteredTools.length} tool{filteredTools.length !== 1 ? 's' : ''} available</>
              )}
            </div>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button onClick={handleAdd} disabled={selectedCount === 0}>
                Add {selectedCount > 0 && `(${selectedCount})`}
              </Button>
            </div>
          </DialogScrollFooter>
        )}
      </DialogScrollContent>
    </Dialog>
  );
}

