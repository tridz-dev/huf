import { useEffect, useState, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Form } from '../components/ui/form';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { toast } from 'sonner';
import { AIProvider, AIModel, AgentToolFunctionRef } from '../types/agent.types';
import { getAgent, updateAgent, createAgent, getAgentTriggers, getAgentTrigger, createAgentTrigger, updateAgentTrigger, getDocTypes, getTriggerTypes, type AgentTriggerListItem, type AgentTriggerDoc, type TriggerTypeOption, deleteAgentTrigger, runAgentTest } from '../services/agentApi';
import { getProviders, getModels } from '../services/providerApi';
import { getToolFunctions, getToolTypes } from '../services/toolApi';
import type { AgentDoc } from '../types/agent.types';
import type { AgentToolType } from '../types/agent.types';
import { SelectToolsModal } from '../components/tools';
import { TriggerModal } from '../components/agent/TriggerModal';
import { getFrappeErrorMessage } from '../lib/frappe-error';
import { AgentHeader } from '../components/agent/AgentHeader';
import { GeneralTab } from '../components/agent/GeneralTab';
import { BehaviorTab } from '../components/agent/BehaviorTab';
import { TriggersTab } from '../components/agent/TriggersTab';
import { ToolsTab } from '../components/agent/ToolsTab';
import { agentFormSchema, type AgentFormValues } from '../components/agent/types';


export function AgentFormPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const isNew = id === 'new';
  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);
  const [deletingTrigger, setDeletingTrigger] = useState(false);
  const [providers, setProviders] = useState<AIProvider[]>([]);
  const [models, setModels] = useState<AIModel[]>([]);
  const [triggers, setTriggers] = useState<AgentTriggerListItem[]>([]);
  const [showTriggerModal, setShowTriggerModal] = useState(false);
  const [editingTrigger, setEditingTrigger] = useState<AgentTriggerDoc | null>(null);
  const [triggerFilter, setTriggerFilter] = useState<string>('all');
  const [triggerStatusFilter, setTriggerStatusFilter] = useState<string>('all');
  const [optimizingPrompt, setOptimizingPrompt] = useState(false);
  const [showToolsModal, setShowToolsModal] = useState(false);
  const [selectedTools, setSelectedTools] = useState<AgentToolFunctionRef[]>([]);
  const [initialTools, setInitialTools] = useState<AgentToolFunctionRef[]>([]); // Track initial tools state
  const [toolTypes, setToolTypes] = useState<AgentToolType[]>([]);
  const [initialDisabled, setInitialDisabled] = useState(false); // Track initial disabled state
  const [docTypes, setDocTypes] = useState<Array<{ name: string }>>([]);
  const [loadingDocTypes, setLoadingDocTypes] = useState(false);
  const [triggerTypes, setTriggerTypes] = useState<TriggerTypeOption[]>([]);
  const [loadingTriggerTypes, setLoadingTriggerTypes] = useState(false);

  const form = useForm<AgentFormValues>({
    resolver: zodResolver(agentFormSchema),
      defaultValues: {
        agent_name: '',
        provider: '',
        model: '',
        temperature: 1,
        top_p: 1,
        disabled: false,
        allow_chat: true,
        persist_conversation: true,
        persist_user_history: true,
        enable_multi_run: false,
        description: '',
        instructions: '',
      },
  });

  const watchProvider = form.watch('provider');
  const watchDisabled = form.watch('disabled');
  const isDirty = form.formState.isDirty;
  
  // Check if tools have changed by comparing tool names
  const toolsChanged = useMemo(() => {
    if (isNew) return selectedTools.length > 0; // New agent with tools selected
    const initialToolNames = new Set(initialTools.map((t) => t.name));
    const currentToolNames = new Set(selectedTools.map((t) => t.name));
    
    if (initialToolNames.size !== currentToolNames.size) return true;
    
    for (const name of currentToolNames) {
      if (!initialToolNames.has(name)) return true;
    }
    
    return false;
  }, [selectedTools, initialTools, isNew]);
  
  // Check if disabled state has changed
  const disabledChanged = useMemo(() => {
    if (isNew) return watchDisabled !== false; // New agent with disabled changed
    return watchDisabled !== initialDisabled;
  }, [watchDisabled, initialDisabled, isNew]);
  
  // Show save button for new agents, when form is dirty, when tools have changed, or when disabled changed
  const showSaveButton = isNew || isDirty || toolsChanged || disabledChanged;

  // Load trigger types on mount
  useEffect(() => {
    if (triggerTypes.length === 0 && !loadingTriggerTypes) {
      setLoadingTriggerTypes(true);
      getTriggerTypes()
        .then((data) => {
          // Ensure data is an array before setting state
          if (Array.isArray(data)) {
            // Filter out any types that don't have a name
            const triggerTypes = data.filter((type) => (type.name));
            setTriggerTypes(triggerTypes);
          } else {
            console.error('getTriggerTypes returned non-array:', data);
            setTriggerTypes([]);
          }
          setLoadingTriggerTypes(false);
        })
        .catch((error) => {
          console.error('Error loading trigger types:', error);
          setTriggerTypes([]);
          setLoadingTriggerTypes(false);
        });
    }
  }, [triggerTypes.length, loadingTriggerTypes]);

  // Load DocTypes when modal opens
  useEffect(() => {
    if (showTriggerModal && docTypes.length === 0 && !loadingDocTypes) {
      setLoadingDocTypes(true);
      getDocTypes()
        .then((data) => {
          setDocTypes(data);
          setLoadingDocTypes(false);
        })
        .catch((error) => {
          console.error('Error loading DocTypes:', error);
          setLoadingDocTypes(false);
        });
    }
  }, [showTriggerModal, docTypes.length, loadingDocTypes]);

  // Load providers, models, and tool types on mount
  useEffect(() => {
    Promise.all([
      getProviders(),
      getModels(),
      getToolTypes(),
    ]).then(([providersData, modelsData, toolTypesData]) => {
      setProviders(providersData);
      setModels(modelsData);
      setToolTypes(toolTypesData);
    }).catch((error) => {
      console.error('Error loading providers/models/types:', error);
      toast.error('Failed to load providers and models');
    });
  }, []);

  // Load models when provider changes
  useEffect(() => {
    if (watchProvider) {
      getModels(watchProvider).then((modelsData) => {
        setModels(modelsData);
        // Clear model selection if current model doesn't belong to selected provider
        const currentModel = form.getValues('model');
        if (currentModel && !modelsData.find(m => m.name === currentModel)) {
          form.setValue('model', '');
        }
      }).catch((error) => {
        console.error('Error loading models:', error);
      });
    } else {
      setModels([]);
    }
  }, [watchProvider, form]);

  // Load agent data when id is available (only for edit mode)
  useEffect(() => {
    if (id && !isNew) {
      getAgent(id).then((data: AgentDoc) => {
        form.reset({
          agent_name: data.agent_name || '',
          provider: data.provider || '',
          model: data.model || '',
          temperature: data.temperature ?? 1,
          top_p: data.top_p ?? 1,
          disabled: data.disabled === 1,
          allow_chat: data.allow_chat === 1,
          persist_conversation: data.persist_conversation === 1,
          persist_user_history: data.persist_user_history === 1,
          enable_multi_run: data.enable_multi_run === 1,
          description: data.description || '',
          instructions: data.instructions || '',
        });
        // Track initial disabled state
        setInitialDisabled(data.disabled === 1);
        // Load tools from agent_tool field
        // agent_tool is a child table with format: [{ tool: "tool-name" }, ...]
        if (data.agent_tool && Array.isArray(data.agent_tool) && data.agent_tool.length > 0) {
          // Fetch full tool details for each tool reference
          const toolNames = data.agent_tool.map((item: any) => item.tool).filter(Boolean);
          if (toolNames.length > 0) {
            getToolFunctions()
              .then((allTools) => {
                const tools = allTools.filter((tool) => toolNames.includes(tool.name));
                setSelectedTools(tools);
                setInitialTools(tools); // Store initial tools state for change detection
              })
              .catch((error) => {
                console.error('Error loading tool details:', error);
                setSelectedTools([]);
                setInitialTools([]);
              });
          } else {
            setSelectedTools([]);
            setInitialTools([]);
          }
        } else {
          setSelectedTools([]);
          setInitialTools([]);
        }
        // Load triggers from Agent Trigger doctype
        getAgentTriggers(id).then((triggersData) => {
          setTriggers(triggersData);
        }).catch((error) => {
          console.error('Error loading triggers:', error);
          // Don't show error toast for triggers, just log it
          setTriggers([]);
        });
        setLoading(false);
      }).catch((error) => {
        console.error('Error loading agent:', error);
        const errorMessage = getFrappeErrorMessage(error);
        toast.error(errorMessage || 'Failed to load agent details');
        setLoading(false);
      });
    } else if (isNew) {
      // New agent mode - form already has default values
      setSelectedTools([]);
      setInitialTools([]);
      setInitialDisabled(false);
      setLoading(false);
    }
  }, [id, isNew, form]);

  const onSubmit = async (values: AgentFormValues) => {
    setSaving(true);
    try {
      // Convert form values (booleans) to AgentDoc format (numbers 0/1)
      const agentData: Partial<AgentDoc> = {
        agent_name: values.agent_name,
        provider: values.provider,
        model: values.model,
        temperature: values.temperature,
        top_p: values.top_p,
        disabled: values.disabled ? 1 : 0,
        allow_chat: values.allow_chat ? 1 : 0,
        persist_conversation: values.persist_conversation ? 1 : 0,
        persist_user_history: values.persist_user_history ? 1 : 0,
        enable_multi_run: values.enable_multi_run ? 1 : 0,
        description: values.description || '',
        instructions: values.instructions,
        // Include tools - Frappe child table format: array of objects with 'tool' field pointing to Agent Tool Function name
        agent_tool: selectedTools.map((tool) => ({
          tool: tool.name,
        })) as any,
      };

      if (isNew) {
        // Create new agent
        const newAgent = await createAgent(agentData);
        toast.success('Agent created successfully!');
        // Reset form state with the created agent's values
        form.reset({
          agent_name: newAgent.agent_name || '',
          provider: newAgent.provider || '',
          model: newAgent.model || '',
          temperature: newAgent.temperature ?? 1,
          top_p: newAgent.top_p ?? 1,
          disabled: newAgent.disabled === 1,
          allow_chat: newAgent.allow_chat === 1,
          persist_conversation: newAgent.persist_conversation === 1,
          persist_user_history: newAgent.persist_user_history === 1,
          enable_multi_run: newAgent.enable_multi_run === 1,
          description: newAgent.description || '',
          instructions: newAgent.instructions || '',
        });
        setInitialDisabled(newAgent.disabled === 1);
        // Navigate to the edit page with the new agent's ID
        navigate(`/agents/${newAgent.name}`);
      } else if (id) {
        // Update existing agent
        await updateAgent(id, agentData);
        toast.success('Agent updated successfully!');
        // Reset form state with the updated values to mark form as clean
        form.reset({
          agent_name: values.agent_name,
          provider: values.provider,
          model: values.model,
          temperature: values.temperature,
          top_p: values.top_p,
          disabled: values.disabled,
          allow_chat: values.allow_chat,
          persist_conversation: values.persist_conversation,
          persist_user_history: values.persist_user_history,
          enable_multi_run: values.enable_multi_run,
          description: values.description,
          instructions: values.instructions,
        });
        // Reset tools and disabled state after successful update to mark as unchanged
        setInitialTools([...selectedTools]);
        setInitialDisabled(values.disabled);
      }
    } catch (error) {
      console.error(`Error ${isNew ? 'creating' : 'updating'} agent:`, error);
      const errorMessage = getFrappeErrorMessage(error);
      toast.error(errorMessage || `Failed to ${isNew ? 'create' : 'update'} agent. Please try again.`);
    } finally {
      setSaving(false);
    }
  };

  const handleOptimizePrompt = () => {
    setOptimizingPrompt((value) => value);
    toast.info('Coming Soon!');
    // setOptimizingPrompt(true);
    // setTimeout(() => {
    //   const currentInstructions = form.getValues('instructions');
    //   const optimized = `${currentInstructions}\n\n[Optimized by AI]\n- Enhanced clarity and structure\n- Added specific examples\n- Improved constraint definition`;
    //   form.setValue('instructions', optimized);
    //   setOptimizingPrompt(false);
    //   toast.success('Prompt optimized successfully!');
    // }, 2000);
  };

  const [runningTest, setRunningTest] = useState(false);

  const handleRunTest = async () => {
    if (!id || isNew) {
      toast.error('Please save the agent first before running a test');
      return;
    }

    const values = form.getValues();
    
    // Validate required fields
    if (!values.agent_name || !values.provider || !values.model) {
      toast.error('Please fill in agent name, provider, and model before running a test');
      return;
    }

    setRunningTest(true);
    toast.info('Running...');

    try {
      const response = await runAgentTest({
        agent_name: values.agent_name,
        prompt: values.instructions || '',
        provider: values.provider,
        model: values.model,
      });

      if (response.message?.success && response.message?.agent_run_id) {
        navigate(`/executions/${response.message.agent_run_id}`);
      } else {
        toast.error('Test run completed but no run ID was returned');
      }
    } catch (error) {
      console.error('Error running agent test:', error);
      const errorMessage = getFrappeErrorMessage(error);
      toast.error(errorMessage || 'Failed to run agent test');
    } finally {
      setRunningTest(false);
    }
  };

  const handleDuplicate = () => {
    toast.info('Coming Soon!');
  };

  const handleDelete = () => {
    toast.info('Deleting agent...');
    navigate('/agents');
  };

  const handleViewLogs = () => {
    if (!id || isNew) {
      toast.error('Please save the agent first before viewing logs');
      return;
    }
    navigate(`/executions?agents=${encodeURIComponent(id)}`);
  };

  const handleAddTools = (tools: AgentToolFunctionRef[]) => {
    setSelectedTools([...selectedTools, ...tools]);
  };

  const handleRemoveTool = (toolId: string) => {
    setSelectedTools(selectedTools.filter((t) => t.name !== toolId));
    toast.success('Tool removed');
  };

  const handleAddTrigger = () => {
    setEditingTrigger(null);
    setShowTriggerModal(true);
  };

  const handleEditTrigger = async (trigger: AgentTriggerListItem) => {
    try {
      const fullTrigger = await getAgentTrigger(trigger.name);
      setEditingTrigger(fullTrigger);
      setShowTriggerModal(true);
    } catch (error) {
      console.error('Error loading trigger:', error);
      const errorMessage = getFrappeErrorMessage(error);
      toast.error(errorMessage || 'Failed to load trigger details');
    }
  };

  const handleDeleteTrigger = async (triggerId: string) => {
    setDeletingTrigger(true);
    try {
      await deleteAgentTrigger(triggerId);
      setTriggers(triggers.filter(t => t.name !== triggerId));
      toast.success('Trigger deleted');
    } catch (error) {
      const errorMessage = getFrappeErrorMessage(error);
      toast.error(errorMessage || 'Failed to delete trigger');
    } finally {
      setDeletingTrigger(false);
    }
  };

  const handleSaveTrigger = async (values: {
    trigger_name?: string;
    trigger_type: string;
    active: boolean;
    scheduled_interval?: string;
    interval_count?: string;
    reference_doctype?: string;
    doc_event?: string;
    condition?: string;
    app_name?: string;
    event_name?: string;
  }) => {
    if (!id || id === 'new') {
      toast.error('Please save the agent first before adding triggers');
      return;
    }

    // Validate trigger_name when creating
    if (!editingTrigger && !values.trigger_name) {
      toast.error('Trigger name is required');
      return;
    }

    try {
      const triggerData: Partial<AgentTriggerDoc> = {
        trigger_name: editingTrigger ? editingTrigger.trigger_name : (values.trigger_name || ''),
        trigger_type: values.trigger_type,
        disabled: values.active ? 0 : 1,
        scheduled_interval: values.scheduled_interval,
        interval_count: values.interval_count && values.interval_count.trim() !== '' 
          ? parseInt(values.interval_count, 10) 
          : undefined,
        reference_doctype: values.reference_doctype,
        doc_event: values.doc_event,
        condition: values.condition,
      };

      if (editingTrigger) {
        // Update existing trigger
        await updateAgentTrigger(editingTrigger.name, triggerData);
        toast.success('Trigger updated successfully');
      } else {
        // Create new trigger
        triggerData.agent = id;
        await createAgentTrigger(triggerData);
        toast.success('Trigger created successfully');
      }

      // Reload triggers list
      const updatedTriggers = await getAgentTriggers(id);
      setTriggers(updatedTriggers);
      setShowTriggerModal(false);
      setEditingTrigger(null);
    } catch (error) {
      console.error('Error saving trigger:', error);
      const errorMessage = getFrappeErrorMessage(error);
      toast.error(errorMessage || `Failed to ${editingTrigger ? 'update' : 'create'} trigger`);
    }
  };


  const activeTriggerCount = triggers.filter(t => t.status === 'active').length;

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-muted-foreground">Loading agent...</div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto">
      <div className="p-6 space-y-6 max-w-6xl mx-auto">
        <AgentHeader
          form={form}
          watchDisabled={watchDisabled}
          providers={providers}
          models={models}
          activeTriggerCount={activeTriggerCount}
          isNew={isNew}
          showSaveButton={showSaveButton}
          saving={saving}
          runningTest={runningTest}
          onSave={form.handleSubmit(onSubmit)}
          onRunTest={handleRunTest}
          onDuplicate={handleDuplicate}
          onViewLogs={handleViewLogs}
          onDelete={handleDelete}
          agentId={!isNew && id ? id : undefined}
        />

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
            <Tabs defaultValue="general" className="w-full">
              <TabsList className="grid w-full grid-cols-4">
                <TabsTrigger value="general">General</TabsTrigger>
                <TabsTrigger value="behavior">Behavior</TabsTrigger>
                <TabsTrigger value="triggers">Triggers</TabsTrigger>
                <TabsTrigger value="tools">Tools & MCP</TabsTrigger>
              </TabsList>

              <TabsContent value="general" className="space-y-4">
                <GeneralTab form={form} providers={providers} models={models} watchProvider={watchProvider} />
              </TabsContent>

              <TabsContent value="behavior" className="space-y-4">
                <BehaviorTab form={form} optimizingPrompt={optimizingPrompt} onOptimizePrompt={handleOptimizePrompt} />
              </TabsContent>

              <TabsContent value="triggers" className="space-y-4">
                <TriggersTab
                  triggers={triggers}
                  triggerTypes={triggerTypes}
                  triggerFilter={triggerFilter}
                  triggerStatusFilter={triggerStatusFilter}
                  onTriggerFilterChange={setTriggerFilter}
                  onTriggerStatusFilterChange={setTriggerStatusFilter}
                  onAddTrigger={handleAddTrigger}
                  onEditTrigger={handleEditTrigger}
                  onDeleteTrigger={handleDeleteTrigger}
                  deletingTrigger={deletingTrigger}
                />
              </TabsContent>

              <TabsContent value="tools" className="space-y-4">
                <ToolsTab
                  selectedTools={selectedTools}
                  toolTypes={toolTypes}
                  onAddTools={() => setShowToolsModal(true)}
                  onRemoveTool={handleRemoveTool}
                />
              </TabsContent>
            </Tabs>
          </form>
        </Form>
      </div>

      {/* Trigger Modal */}
      <TriggerModal
        open={showTriggerModal}
        onOpenChange={setShowTriggerModal}
        editingTrigger={editingTrigger}
        triggerTypes={triggerTypes}
        docTypes={docTypes}
        loadingDocTypes={loadingDocTypes}
        agentId={id}
        onSave={handleSaveTrigger}
      />

      {/* Select Tools Modal */}
      <SelectToolsModal
        open={showToolsModal}
        onOpenChange={setShowToolsModal}
        selectedTools={selectedTools}
        onAddTools={handleAddTools}
      />
    </div>
  );
}
