import { useState, useEffect, useMemo } from 'react';
import { Search } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog';
import { Input } from '../ui/input';
import { Button } from '../ui/button';
import { Combobox } from '../ui/combobox';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../ui/tabs';
import { ToolCard } from './ToolCard';
import { ToolTemplateCard } from './ToolTemplateCard';
import { ToolCreationForm } from './ToolCreationForm';
import { getToolFunctions, getToolTypes, createToolFunction } from '@/services/toolApi';
import type { AgentToolFunctionRef, AgentToolType } from '@/types/agent.types';
import type { ToolTemplate, ToolFormData } from '@/types/toolTemplate.types';
import { toast } from 'sonner';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import toolTemplatesConfig from '@/config/toolTemplates.json';

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
      ])
        .then(([types, tools]) => {
          setToolTypes(types);
          setAllTools(tools);
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
      { value: 'all', label: 'All Tool Types' },
      ...toolTypes.map((type) => ({
        value: type.name,
        label: type.name1 || type.name,
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
      
      // Auto-select the newly created tool
      const newSelectedIds = new Set(selectedToolIds);
      newSelectedIds.add(newTool.name);
      setSelectedToolIds(newSelectedIds);
      
      // Add the created tool to the agent
      onAddTools([newTool]);
      
      // Switch back to Tool Library tab and reset form view
      setActiveTab('tool-library');
      setCreateView('templates');
      setSelectedTemplate(null);
      
      toast.success('Tool created and added successfully!');
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
      <DialogContent className="sm:max-w-[700px] h-[80vh] flex flex-col p-0 overflow-hidden">
        <DialogHeader className="px-6 pt-6 pb-4 flex-shrink-0">
          <DialogTitle>Add Tool</DialogTitle>
        </DialogHeader>

        {/* Tabs */}
        <Tabs 
          value={activeTab} 
          onValueChange={(value) => setActiveTab(value as 'tool-library' | 'create-new')} 
          className="px-6 flex flex-col flex-1 min-h-0 overflow-hidden"
        >
          <TabsList className="grid w-full grid-cols-2 flex-shrink-0">
            <TabsTrigger value="tool-library">Tool Library</TabsTrigger>
            <TabsTrigger value="create-new">Create New</TabsTrigger>
          </TabsList>

          {/* Tool Library Tab */}
          <TabsContent 
            value="tool-library" 
            className="mt-4 data-[state=active]:flex data-[state=active]:flex-col data-[state=active]:flex-1 data-[state=active]:min-h-0 data-[state=active]:overflow-hidden"
          >
            <DialogDescription className="pb-2 flex-shrink-0">
              Choose tools to add to this agent. Select multiple tools at once.
            </DialogDescription>

            {/* Filters */}
            <div className="flex flex-col gap-3 mb-4 flex-shrink-0">
              {/* Search */}
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
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
                  <div className="text-muted-foreground">Loading tools...</div>
                </div>
              ) : filteredTools.length === 0 ? (
                <div className="flex items-center justify-center py-12">
                  <div className="text-muted-foreground">
                    {searchQuery || toolTypeFilter !== 'all'
                      ? 'No tools match your filters'
                      : 'No tools available'}
                  </div>
                </div>
              ) : (
                filteredTools.map((tool) => (
                  <ToolCard
                    key={tool.name}
                    tool={tool}
                    selected={selectedToolIds.has(tool.name)}
                    onSelect={handleToolToggle}
                    compact
                    toolTypesMap={toolTypesMap}
                  />
                ))
              )}
            </div>

            {/* Footer */}
            <DialogFooter className="flex items-center justify-between border-t pt-4 mt-4 flex-shrink-0">
              <div className="text-sm text-muted-foreground">
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
            </DialogFooter>
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
      </DialogContent>
    </Dialog>
  );
}

