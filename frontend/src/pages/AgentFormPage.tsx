import { useEffect, useState, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import {
  Play,
  Save,
  MoreVertical,
  Copy,
  Trash2,
  FileText,
  Plus,
  Edit,
  Clock,
  Sparkles,
  Filter,
  Server,
  Plug,
  MessageSquare,
} from 'lucide-react';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Switch } from '../components/ui/switch';
import { Input } from '../components/ui/input';
import { Textarea } from '../components/ui/textarea';
import { Slider } from '../components/ui/slider';
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '../components/ui/form';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../components/ui/select';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '../components/ui/dropdown-menu';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { toast } from 'sonner';
import { AIProvider, AIModel, AgentToolFunctionRef } from '../types/agent.types';
import { getAgent, updateAgent, createAgent, getAgentTriggers, getAgentTrigger, createAgentTrigger, updateAgentTrigger, getDocTypes, getTriggerTypes, type AgentTriggerListItem, type AgentTriggerDoc, type TriggerTypeOption } from '../services/agentApi';
import { getProviders, getModels } from '../services/providerApi';
import { getToolFunctions, getToolTypes } from '../services/toolApi';
import type { AgentDoc } from '../types/agent.types';
import type { AgentToolType } from '../types/agent.types';
import { SelectToolsModal } from '../components/tools';
import { TriggerModal } from '../components/agent/TriggerModal';
import { getFrappeErrorMessage } from '../lib/frappe-error';

const agentFormSchema = z.object({
  agent_name: z.string().min(1, 'Agent name is required'),
  provider: z.string().min(1, 'Provider is required'),
  model: z.string().min(1, 'Model is required'),
  temperature: z.number().min(0).max(2),
  top_p: z.number().min(0).max(1),
  disabled: z.boolean(),
  allow_chat: z.boolean(),
  persist_conversation: z.boolean(),
  description: z.string().optional(),
  instructions: z.string(),
});

type AgentFormValues = z.infer<typeof agentFormSchema>;

const mockMCPs = [
  { id: 'm1', name: 'Zendesk MCP', description: 'Query and manage Zendesk tickets', provider: 'Zendesk', status: 'connected' },
  { id: 'm2', name: 'Slack MCP', description: 'Send messages and read channels', provider: 'Slack', status: 'connected' },
  { id: 'm3', name: 'PostgreSQL MCP', description: 'Query customer database', provider: 'PostgreSQL', status: 'connected' },
  { id: 'm4', name: 'Stripe MCP', description: 'Access payment and subscription data', provider: 'Stripe', status: 'inactive' },
];


export function AgentFormPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const isNew = id === 'new';
  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);
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
    setOptimizingPrompt(true);
    setTimeout(() => {
      const currentInstructions = form.getValues('instructions');
      const optimized = `${currentInstructions}\n\n[Optimized by AI]\n- Enhanced clarity and structure\n- Added specific examples\n- Improved constraint definition`;
      form.setValue('instructions', optimized);
      setOptimizingPrompt(false);
      toast.success('Prompt optimized successfully!');
    }, 2000);
  };

  const handleRunTest = () => {
    toast.info('Running test...');
  };

  const handleDuplicate = () => {
    toast.info('Duplicating agent...');
  };

  const handleDelete = () => {
    toast.info('Deleting agent...');
    navigate('/agents');
  };

  const handleViewLogs = () => {
    toast.info('Opening logs...');
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

  const handleDeleteTrigger = (triggerId: string) => {
    setTriggers(triggers.filter(t => t.name !== triggerId));
    toast.success('Trigger deleted');
  };

  const handleSaveTrigger = async (values: {
    trigger_name?: string;
    trigger_type: string;
    active: boolean;
    scheduled_interval?: string;
    interval_count?: number;
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
        interval_count: values.interval_count,
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


  const filteredTriggers = triggers.filter(trigger => {
    if (triggerFilter !== 'all' && trigger.type !== triggerFilter) return false;
    if (triggerStatusFilter === 'active' && trigger.status !== 'active') return false;
    if (triggerStatusFilter === 'disabled' && trigger.status === 'active') return false;
    return true;
  });

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
        {/* Header */}
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div className="flex-1 space-y-2">
            <div className="flex items-center gap-3 flex-wrap">
              <Input
                value={form.watch('agent_name')}
                onChange={(e) => form.setValue('agent_name', e.target.value, { shouldDirty: true })}
                className="text-2xl font-bold h-auto border-0 px-0 focus-visible:ring-0 max-w-md"
                placeholder="Agent Name"
              />
              <Badge variant={watchDisabled ? 'secondary' : 'default'}>
                {watchDisabled ? 'Disabled' : 'Active'}
              </Badge>
              <Badge variant="outline">
                {providers.find(p => p.name === form.watch('provider'))?.provider_name || form.watch('provider') || 'Provider'}
              </Badge>
              <Badge variant="outline">
                {models.find(m => m.name === form.watch('model'))?.model_name || form.watch('model') || 'Model'}
              </Badge>
            </div>
            {activeTriggerCount > 0 && (
              <div className="text-sm text-muted-foreground flex items-center gap-2">
                <Clock className="w-4 h-4" />
                {activeTriggerCount} active {activeTriggerCount === 1 ? 'trigger' : 'triggers'}
              </div>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="icon" onClick={handleRunTest} type="button">
              <Play className="w-4 h-4" />
            </Button>
            <Button variant="outline" size="sm" type="button">
              <MessageSquare className="w-4 h-4 mr-2" />
              Chat
            </Button>
            {showSaveButton && (
              <Button size="sm" onClick={form.handleSubmit(onSubmit)} disabled={saving}>
                <Save className="w-4 h-4 mr-2" />
                {saving ? (isNew ? 'Creating...' : 'Saving...') : (isNew ? 'Create' : 'Save')}
              </Button>
            )}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="sm">
                  <MoreVertical className="w-4 h-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <div className="px-2 py-1.5">
                  <div className="flex items-center justify-between">
                    <span className="text-sm">Disable</span>
                    <Switch 
                      checked={watchDisabled} 
                      onCheckedChange={(checked) => form.setValue('disabled', checked)}
                      onClick={(e) => e.stopPropagation()}
                    />
                  </div>
                </div>
                {!isNew && (
                  <>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem onClick={handleDuplicate}>
                      <Copy className="w-4 h-4 mr-2" />
                      Duplicate
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={handleViewLogs}>
                      <FileText className="w-4 h-4 mr-2" />
                      View Logs
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={handleDelete} className="text-destructive">
                      <Trash2 className="w-4 h-4 mr-2" />
                      Delete
                    </DropdownMenuItem>
                  </>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
            <Tabs defaultValue="general" className="w-full">
              <TabsList className="grid w-full grid-cols-4">
                <TabsTrigger value="general">General</TabsTrigger>
                <TabsTrigger value="behavior">Behavior</TabsTrigger>
                <TabsTrigger value="triggers">Triggers</TabsTrigger>
                <TabsTrigger value="tools">Tools & MCP</TabsTrigger>
              </TabsList>

              {/* General Tab */}
              <TabsContent value="general" className="space-y-4">
                <Card>
                  <CardHeader>
                    <CardTitle>LLM Configuration</CardTitle>
                    <CardDescription>Configure language model settings</CardDescription>
                  </CardHeader>
                  <CardContent className="grid gap-6 sm:grid-cols-2">
                    <FormField
                      control={form.control}
                      name="agent_name"
                      render={({ field }) => (
                        <FormItem className="sm:col-span-2">
                          <FormLabel>Agent Name</FormLabel>
                          <FormControl>
                            <Input placeholder="my-agent" {...field} />
                          </FormControl>
                          <FormDescription>Unique agent name</FormDescription>
                          <FormMessage />
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
                              placeholder="A short summary describing what this agent does or is designed for."
                              className="min-h-[80px] resize-y"
                              {...field}
                            />
                          </FormControl>
                          <FormDescription>A brief description of the agent's purpose</FormDescription>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    <FormField
                      control={form.control}
                      name="provider"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Provider</FormLabel>
                          <Select
                            onValueChange={(value) => {
                              field.onChange(value);
                              form.setValue('model', '');
                            }}
                            value={field.value}
                          >
                            <FormControl>
                              <SelectTrigger>
                                <SelectValue placeholder="Select provider" />
                              </SelectTrigger>
                            </FormControl>
                            <SelectContent>
                              {providers.map((provider) => (
                                <SelectItem key={provider.name} value={provider.name}>
                                  {provider.provider_name || provider.name}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    <FormField
                      control={form.control}
                      name="model"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Model</FormLabel>
                          <Select
                            onValueChange={field.onChange}
                            value={field.value}
                            disabled={!watchProvider}
                          >
                            <FormControl>
                              <SelectTrigger>
                                <SelectValue placeholder="Select model" />
                              </SelectTrigger>
                            </FormControl>
                            <SelectContent>
                              {models
                                .filter((model) => model.provider === watchProvider)
                                .map((model) => (
                                  <SelectItem key={model.name} value={model.name}>
                                    {model.model_name || model.name}
                                  </SelectItem>
                                ))}
                            </SelectContent>
                          </Select>
                          <FormDescription>Filtered by selected provider</FormDescription>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    <FormField
                      control={form.control}
                      name="temperature"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Temperature: {field.value}</FormLabel>
                          <FormControl>
                            <Slider
                              min={0}
                              max={2}
                              step={0.1}
                              value={[field.value]}
                              onValueChange={(vals) => field.onChange(vals[0])}
                            />
                          </FormControl>
                          <FormDescription>
                            Lower = focused, higher = creative
                          </FormDescription>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    <FormField
                      control={form.control}
                      name="top_p"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Top P: {field.value}</FormLabel>
                          <FormControl>
                            <Slider
                              min={0}
                              max={1}
                              step={0.05}
                              value={[field.value]}
                              onValueChange={(vals) => field.onChange(vals[0])}
                            />
                          </FormControl>
                          <FormDescription>
                            Nucleus sampling parameter
                          </FormDescription>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </CardContent>
                </Card>
              </TabsContent>

              {/* Behavior Tab */}
              <TabsContent value="behavior" className="space-y-4">
                <Card>
                  <CardHeader>
                    <CardTitle>Conversation Settings</CardTitle>
                    <CardDescription>Configure conversation behavior</CardDescription>
                  </CardHeader>
                  <CardContent className="grid gap-4 sm:grid-cols-2">
                    <FormField
                      control={form.control}
                      name="allow_chat"
                      render={({ field }) => (
                        <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                          <div className="space-y-0.5">
                            <FormLabel className="text-base">Allow Chat</FormLabel>
                            <FormDescription>
                              Enable in Chat window
                            </FormDescription>
                          </div>
                          <FormControl>
                            <Switch checked={field.value} onCheckedChange={field.onChange} />
                          </FormControl>
                        </FormItem>
                      )}
                    />

                    <FormField
                      control={form.control}
                      name="persist_conversation"
                      render={({ field }) => (
                        <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                          <div className="space-y-0.5">
                            <FormLabel className="text-base">Persist History</FormLabel>
                            <FormDescription>
                              Save conversation logs
                            </FormDescription>
                          </div>
                          <FormControl>
                            <Switch checked={field.value} onCheckedChange={field.onChange} />
                          </FormControl>
                        </FormItem>
                      )}
                    />
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle>Instructions</CardTitle>
                    <CardDescription>Define system prompt, goals, and constraints</CardDescription>
                  </CardHeader>
                  <CardContent className="relative">
                    <FormField
                      control={form.control}
                      name="instructions"
                      render={({ field }) => (
                        <FormItem>
                          <FormControl>
                            <Textarea
                              placeholder="Define system prompt, goals, constraints..."
                              className="min-h-[300px] font-mono resize-y"
                              {...field}
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <Button
                      type="button"
                      size="sm"
                      variant="secondary"
                      className="absolute top-6 right-10"
                      onClick={handleOptimizePrompt}
                      disabled={optimizingPrompt}
                    >
                      <Sparkles className="w-4 h-4 mr-2" />
                      {optimizingPrompt ? 'Optimizing...' : 'Optimize'}
                    </Button>
                  </CardContent>
                </Card>
              </TabsContent>

              {/* Triggers Tab */}
              <TabsContent value="triggers" className="space-y-4">
                <Card>
                  <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
                    <div className="space-y-1.5">
                      <CardTitle>Agent Triggers</CardTitle>
                      <CardDescription>
                        Define multiple ways this agent can run
                      </CardDescription>
                    </div>
                    <Button onClick={handleAddTrigger} size="sm" type="button">
                      <Plus className="w-4 h-4 mr-2" />
                      Add Trigger
                    </Button>
                  </CardHeader>
                  <CardContent>
                    {triggers.length === 0 ? (
                      <div className="text-center py-12">
                        <p className="text-muted-foreground mb-4">No triggers added yet.</p>
                        <Button onClick={handleAddTrigger} variant="outline" type="button">
                          <Plus className="w-4 h-4 mr-2" />
                          Add Trigger
                        </Button>
                      </div>
                    ) : (
                      <>
                        <div className="flex items-center gap-3 mb-4">
                          <div className="flex items-center gap-2">
                            <Filter className="w-4 h-4 text-muted-foreground" />
                            <Select value={triggerFilter} onValueChange={setTriggerFilter}>
                              <SelectTrigger className="w-[180px]">
                                <SelectValue placeholder="Filter by type" />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="all">All Types</SelectItem>
                                {Array.isArray(triggerTypes) && triggerTypes.map((type) => (
                                  <SelectItem key={type.name} value={type.name}>
                                    {type.name}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </div>
                          <Select value={triggerStatusFilter} onValueChange={setTriggerStatusFilter}>
                            <SelectTrigger className="w-[150px]">
                              <SelectValue placeholder="Filter by status" />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="all">All Status</SelectItem>
                              <SelectItem value="active">Active</SelectItem>
                              <SelectItem value="disabled">Disabled</SelectItem>
                            </SelectContent>
                          </Select>
                          <div className="text-sm text-muted-foreground ml-auto">
                            {filteredTriggers.length} of {triggers.length} triggers
                          </div>
                        </div>
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>Type</TableHead>
                              <TableHead>Details</TableHead>
                              <TableHead>Status</TableHead>
                              <TableHead>Last Run</TableHead>
                              <TableHead>Next Run</TableHead>
                              <TableHead className="text-right">Actions</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {filteredTriggers.map((trigger) => (
                              <TableRow key={trigger.name}>
                                <TableCell className="font-medium">{trigger.type}</TableCell>
                                <TableCell className="max-w-xs truncate">{trigger.trigger_name}</TableCell>
                                <TableCell>
                                  <Badge variant={trigger.status === 'active' ? 'default' : 'secondary'}>
                                    {trigger.status === 'active' ? 'Active' : 'Disabled'}
                                  </Badge>
                                </TableCell>
                                <TableCell>—</TableCell>
                                <TableCell>—</TableCell>
                                <TableCell className="text-right">
                                  <div className="flex justify-end gap-2">
                                    <Button
                                      type="button"
                                      variant="ghost"
                                      size="sm"
                                      onClick={() => handleEditTrigger(trigger)}
                                    >
                                      <Edit className="w-4 h-4" />
                                    </Button>
                                    <Button
                                      type="button"
                                      variant="ghost"
                                      size="sm"
                                      onClick={() => handleDeleteTrigger(trigger.name)}
                                    >
                                      <Trash2 className="w-4 h-4" />
                                    </Button>
                                  </div>
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </>
                    )}
                  </CardContent>
                </Card>
              </TabsContent>

              {/* Tools & MCP Tab */}
              <TabsContent value="tools" className="space-y-4">
                <Card>
                  <CardHeader>
                    <div className="flex items-center justify-between">
                      <div>
                        <CardTitle className="flex items-center gap-2">
                          <Server className="w-5 h-5" />
                          Tools
                        </CardTitle>
                        <CardDescription>Function tools available to this agent</CardDescription>
                      </div>
                      <Button size="sm" variant="outline" onClick={() => setShowToolsModal(true)} type="button">
                        <Plus className="w-4 h-4 mr-2" />
                        Add Tool
                      </Button>
                    </div>
                  </CardHeader>
                  <CardContent>
                    {selectedTools.length === 0 ? (
                      <div className="text-center py-12">
                        <p className="text-muted-foreground mb-4">No tools added yet.</p>
                        <Button onClick={() => setShowToolsModal(true)} variant="outline" type="button">
                          <Plus className="w-4 h-4 mr-2" />
                          Add Tool
                        </Button>
                      </div>
                    ) : (
                      <div className="grid gap-3 sm:grid-cols-2">
                        {selectedTools.map((tool) => {
                          // Get tool type display name from tool_type link field
                          const toolType = toolTypes.find((tt) => tt.name === tool.tool_type);
                          const toolTypeDisplayName = toolType?.name1;

                          return (
                            <div
                              key={tool.name}
                              className="flex items-start justify-between gap-3 rounded-lg border p-4 hover:bg-muted/50 transition-colors"
                            >
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 mb-1">
                                  <h4 className="font-medium text-sm">{tool.tool_name || tool.name}</h4>
                                  {toolTypeDisplayName && (
                                    <Badge variant="outline" className="text-xs shrink-0">
                                      {toolTypeDisplayName}
                                    </Badge>
                                  )}
                                </div>
                                {tool.description && (
                                  <p className="text-xs text-muted-foreground">{tool.description}</p>
                                )}
                              </div>
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                onClick={() => handleRemoveTool(tool.name)}
                              >
                                <Trash2 className="w-4 h-4" />
                              </Button>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <div className="flex items-center justify-between">
                      <div>
                        <CardTitle className="flex items-center gap-2">
                          <Plug className="w-5 h-5" />
                          Model Context Protocol (MCP)
                        </CardTitle>
                        <CardDescription>Connected MCP servers for extended capabilities</CardDescription>
                      </div>
                      <Button 
                        type="button"
                        size="sm" 
                        variant="outline"
                        onClick={() => toast.info('Coming soon')}
                      >
                        <Plus className="w-4 h-4 mr-2" />
                        Connect MCP
                      </Button>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <div className="grid gap-3">
                      {mockMCPs.map((mcp) => (
                        <div
                          key={mcp.id}
                          className="flex items-start justify-between gap-3 rounded-lg border p-4 hover:bg-muted/50 transition-colors"
                        >
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-1">
                              <h4 className="font-medium text-sm">{mcp.name}</h4>
                              <Badge variant="outline" className="text-xs shrink-0">
                                {mcp.provider}
                              </Badge>
                              <Badge
                                variant={mcp.status === 'connected' ? 'default' : 'secondary'}
                                className="text-xs shrink-0"
                              >
                                {mcp.status}
                              </Badge>
                            </div>
                            <p className="text-xs text-muted-foreground">{mcp.description}</p>
                          </div>
                          <div className="flex items-center gap-2">
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              onClick={() => toast.info('Coming soon')}
                            >
                              <Switch checked={mcp.status === 'connected'} className="pointer-events-none" />
                            </Button>
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              onClick={() => toast.info('Coming soon')}
                            >
                              <Trash2 className="w-4 h-4" />
                            </Button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
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
