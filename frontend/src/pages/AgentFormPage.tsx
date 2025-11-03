import { useEffect, useState } from 'react';
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
import { Label } from '../components/ui/label';
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
  DropdownMenuTrigger,
} from '../components/ui/dropdown-menu';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../components/ui/dialog';
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
import { AgentTrigger, TriggerType, ScheduledInterval, DocEventType } from '../types/agent.types';
import { mockApi } from '../services/mockApi';

const agentFormSchema = z.object({
  agent_name: z.string().min(1, 'Agent name is required'),
  provider: z.string().min(1, 'Provider is required'),
  model: z.string().min(1, 'Model is required'),
  temperature: z.number().min(0).max(2),
  top_p: z.number().min(0).max(1),
  async: z.boolean(),
  disabled: z.boolean(),
  allow_chat: z.boolean(),
  persist_conversation: z.boolean(),
  instructions: z.string(),
});

type AgentFormValues = z.infer<typeof agentFormSchema>;

const triggerFormSchema = z.object({
  trigger_type: z.enum(['Schedule', 'Doc Event', 'Webhook', 'App Event', 'Manual']),
  active: z.boolean(),
  schedule_interval: z.string().optional(),
  interval_count: z.number().int().min(1).optional(),
  reference_doctype: z.string().optional(),
  doc_event: z.string().optional(),
  condition: z.string().optional(),
  app_name: z.string().optional(),
  event_name: z.string().optional(),
}).refine((data) => {
  if (data.trigger_type === 'Schedule') {
    return data.schedule_interval && data.interval_count;
  }
  if (data.trigger_type === 'Doc Event') {
    return data.reference_doctype && data.doc_event;
  }
  if (data.trigger_type === 'App Event') {
    return data.app_name && data.event_name;
  }
  return true;
}, {
  message: "Required fields missing for selected trigger type",
});

type TriggerFormValues = z.infer<typeof triggerFormSchema>;

const providers = [
  { name: 'OpenAI', provider_name: 'openai' },
  { name: 'Anthropic', provider_name: 'anthropic' },
  { name: 'Google', provider_name: 'google' },
];

const models: Record<string, { name: string; model_name: string }[]> = {
  openai: [
    { name: 'GPT-4', model_name: 'gpt-4' },
    { name: 'GPT-4 Turbo', model_name: 'gpt-4-turbo' },
    { name: 'GPT-3.5 Turbo', model_name: 'gpt-3.5-turbo' },
  ],
  anthropic: [
    { name: 'Claude 3 Opus', model_name: 'claude-3-opus' },
    { name: 'Claude 3 Sonnet', model_name: 'claude-3-sonnet' },
    { name: 'Claude 3 Haiku', model_name: 'claude-3-haiku' },
  ],
  google: [
    { name: 'Gemini Pro', model_name: 'gemini-pro' },
    { name: 'Gemini Ultra', model_name: 'gemini-ultra' },
  ],
};

const scheduledIntervals: ScheduledInterval[] = ['Hourly', 'Daily', 'Weekly', 'Monthly', 'Yearly'];

const docEvents: DocEventType[] = [
  'before_insert', 'after_insert', 'validate', 'before_save', 'after_save',
  'before_submit', 'on_submit', 'after_submit', 'on_cancel', 'before_rename',
  'after_rename', 'on_trash', 'after_delete',
];

const triggerTypes: TriggerType[] = ['Schedule', 'Doc Event', 'Webhook', 'App Event', 'Manual'];

const mockTools = [
  { id: '1', name: 'Create Helpdesk Ticket', description: 'Create support tickets in helpdesk system', category: 'Support', status: 'active' },
  { id: '2', name: 'Fetch Invoices', description: 'Retrieve invoice data from accounting system', category: 'Finance', status: 'active' },
  { id: '3', name: 'Send Email', description: 'Send email notifications to customers', category: 'Communication', status: 'active' },
  { id: '4', name: 'Send WhatsApp', description: 'Send WhatsApp messages via Business API', category: 'Communication', status: 'active' },
];

const mockMCPs = [
  { id: 'm1', name: 'Zendesk MCP', description: 'Query and manage Zendesk tickets', provider: 'Zendesk', status: 'connected' },
  { id: 'm2', name: 'Slack MCP', description: 'Send messages and read channels', provider: 'Slack', status: 'connected' },
  { id: 'm3', name: 'PostgreSQL MCP', description: 'Query customer database', provider: 'PostgreSQL', status: 'connected' },
  { id: 'm4', name: 'Stripe MCP', description: 'Access payment and subscription data', provider: 'Stripe', status: 'inactive' },
];

export function AgentFormPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [triggers, setTriggers] = useState<AgentTrigger[]>([]);
  const [showTriggerModal, setShowTriggerModal] = useState(false);
  const [editingTrigger, setEditingTrigger] = useState<AgentTrigger | null>(null);
  const [triggerFilter, setTriggerFilter] = useState<string>('all');
  const [triggerStatusFilter, setTriggerStatusFilter] = useState<string>('all');
  const [optimizingPrompt, setOptimizingPrompt] = useState(false);

  const form = useForm<AgentFormValues>({
    resolver: zodResolver(agentFormSchema),
    defaultValues: {
      agent_name: '',
      provider: '',
      model: '',
      temperature: 1,
      top_p: 1,
      async: false,
      disabled: false,
      allow_chat: true,
      persist_conversation: true,
      instructions: '',
    },
  });

  const triggerForm = useForm<TriggerFormValues>({
    resolver: zodResolver(triggerFormSchema),
    defaultValues: {
      trigger_type: 'Schedule',
      active: true,
      interval_count: 1,
    },
  });

  const watchProvider = form.watch('provider');
  const watchDisabled = form.watch('disabled');
  const watchTriggerType = triggerForm.watch('trigger_type');

  useEffect(() => {
    if (id) {
      mockApi.agents.get(id).then((data) => {
        if (data) {
          form.reset({
            agent_name: data.agent_name,
            provider: data.provider,
            model: data.model,
            temperature: data.temperature ?? 1,
            top_p: data.top_p ?? 1,
            async: data.async ?? false,
            disabled: data.disabled ?? false,
            allow_chat: data.allow_chat ?? true,
            persist_conversation: data.persist_conversation ?? true,
            instructions: data.instructions,
          });
          setTriggers(data.triggers || []);
        }
        setLoading(false);
      });
    } else {
      setLoading(false);
    }
  }, [id, form]);

  const onSubmit = (values: AgentFormValues) => {
    console.log('Form values:', values);
    console.log('Triggers:', triggers);
    toast.success('Agent saved successfully!');
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

  const handleAddTrigger = () => {
    setEditingTrigger(null);
    triggerForm.reset({
      trigger_type: 'Schedule',
      active: true,
      interval_count: 1,
    });
    setShowTriggerModal(true);
  };

  const handleEditTrigger = (trigger: AgentTrigger) => {
    setEditingTrigger(trigger);
    triggerForm.reset({
      trigger_type: trigger.trigger_type,
      active: trigger.active,
      schedule_interval: trigger.schedule_interval,
      interval_count: trigger.interval_count,
      reference_doctype: trigger.reference_doctype,
      doc_event: trigger.doc_event,
      condition: trigger.condition,
      app_name: trigger.app_name,
      event_name: trigger.event_name,
    });
    setShowTriggerModal(true);
  };

  const handleDeleteTrigger = (triggerId: string) => {
    setTriggers(triggers.filter(t => t.id !== triggerId));
    toast.success('Trigger deleted');
  };

  const handleSaveTrigger = (values: TriggerFormValues) => {
    if (editingTrigger) {
      setTriggers(triggers.map(t =>
        t.id === editingTrigger.id
          ? {
              ...t,
              trigger_type: values.trigger_type,
              active: values.active,
              schedule_interval: values.schedule_interval as ScheduledInterval | undefined,
              interval_count: values.interval_count,
              reference_doctype: values.reference_doctype,
              doc_event: values.doc_event as DocEventType | undefined,
              condition: values.condition,
              app_name: values.app_name,
              event_name: values.event_name,
              updated_at: new Date().toISOString()
            }
          : t
      ));
      toast.success('Trigger updated');
    } else {
      const newTrigger: AgentTrigger = {
        id: `trigger-${Date.now()}`,
        trigger_type: values.trigger_type,
        active: values.active,
        schedule_interval: values.schedule_interval as ScheduledInterval | undefined,
        interval_count: values.interval_count,
        reference_doctype: values.reference_doctype,
        doc_event: values.doc_event as DocEventType | undefined,
        condition: values.condition,
        app_name: values.app_name,
        event_name: values.event_name,
        webhook_url: values.trigger_type === 'Webhook'
          ? `https://api.hufai.com/agent/${id}/webhook/${Date.now()}`
          : undefined,
        created_at: new Date().toISOString(),
      };
      setTriggers([...triggers, newTrigger]);
      toast.success('Trigger added');
    }
    setShowTriggerModal(false);
  };

  const getTriggerDetails = (trigger: AgentTrigger): string => {
    switch (trigger.trigger_type) {
      case 'Schedule':
        return `${trigger.schedule_interval} × ${trigger.interval_count}`;
      case 'Doc Event':
        return `${trigger.reference_doctype} → ${trigger.doc_event}`;
      case 'Webhook':
        return trigger.webhook_url?.split('/').pop() || 'Webhook';
      case 'App Event':
        return `${trigger.app_name} → ${trigger.event_name}`;
      case 'Manual':
        return 'Manual trigger';
      default:
        return '';
    }
  };

  const getLastRun = (trigger: AgentTrigger): string => {
    if (trigger.last_execution) {
      const date = new Date(trigger.last_execution);
      const now = new Date();
      const diff = Math.floor((now.getTime() - date.getTime()) / 1000 / 60);
      if (diff < 60) return `${diff}m ago`;
      if (diff < 1440) return `${Math.floor(diff / 60)}h ago`;
      return `${Math.floor(diff / 1440)}d ago`;
    }
    return '—';
  };

  const getNextRun = (trigger: AgentTrigger): string => {
    if (trigger.next_execution) {
      const date = new Date(trigger.next_execution);
      const now = new Date();
      const diff = Math.floor((date.getTime() - now.getTime()) / 1000 / 60);
      if (diff < 60) return `${diff}m`;
      if (diff < 1440) return `${Math.floor(diff / 60)}h`;
      return `${Math.floor(diff / 1440)}d`;
    }
    return '—';
  };

  const filteredTriggers = triggers.filter(trigger => {
    if (triggerFilter !== 'all' && trigger.trigger_type !== triggerFilter) return false;
    if (triggerStatusFilter === 'active' && !trigger.active) return false;
    if (triggerStatusFilter === 'inactive' && trigger.active) return false;
    return true;
  });

  const activeTriggerCount = triggers.filter(t => t.active).length;

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
                onChange={(e) => form.setValue('agent_name', e.target.value)}
                className="text-2xl font-bold h-auto border-0 px-0 focus-visible:ring-0 max-w-md"
                placeholder="Agent Name"
              />
              <Badge variant={watchDisabled ? 'secondary' : 'default'}>
                {watchDisabled ? 'Disabled' : 'Active'}
              </Badge>
              <Badge variant="outline">{form.watch('provider') || 'Provider'}</Badge>
              <Badge variant="outline">{form.watch('model') || 'Model'}</Badge>
            </div>
            {activeTriggerCount > 0 && (
              <div className="text-sm text-muted-foreground flex items-center gap-2">
                <Clock className="w-4 h-4" />
                {activeTriggerCount} active {activeTriggerCount === 1 ? 'trigger' : 'triggers'}
              </div>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="icon" onClick={handleRunTest}>
              <Play className="w-4 h-4" />
            </Button>
            <Button variant="outline" size="sm">
              <MessageSquare className="w-4 h-4 mr-2" />
              Chat
            </Button>
            <Button size="sm" onClick={form.handleSubmit(onSubmit)}>
              <Save className="w-4 h-4 mr-2" />
              Save
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="sm">
                  <MoreVertical className="w-4 h-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={handleDuplicate}>
                  <Copy className="w-4 h-4 mr-2" />
                  Duplicate
                </DropdownMenuItem>
                <DropdownMenuItem onClick={handleViewLogs}>
                  <FileText className="w-4 h-4 mr-2" />
                  View Logs
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={() => form.setValue('disabled', !watchDisabled)}
                >
                  <Switch
                    checked={watchDisabled}
                    className="mr-2 pointer-events-none"
                  />
                  Disable
                </DropdownMenuItem>
                <DropdownMenuItem onClick={handleDelete} className="text-destructive">
                  <Trash2 className="w-4 h-4 mr-2" />
                  Delete
                </DropdownMenuItem>
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
                                <SelectItem key={provider.provider_name} value={provider.provider_name}>
                                  {provider.name}
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
                              {watchProvider &&
                                models[watchProvider]?.map((model) => (
                                  <SelectItem key={model.model_name} value={model.model_name}>
                                    {model.name}
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
                    <Button onClick={handleAddTrigger} size="sm">
                      <Plus className="w-4 h-4 mr-2" />
                      Add Trigger
                    </Button>
                  </CardHeader>
                  <CardContent>
                    {triggers.length === 0 ? (
                      <div className="text-center py-12">
                        <p className="text-muted-foreground mb-4">No triggers added yet.</p>
                        <Button onClick={handleAddTrigger} variant="outline">
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
                                {triggerTypes.map((type) => (
                                  <SelectItem key={type} value={type}>
                                    {type}
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
                              <SelectItem value="inactive">Inactive</SelectItem>
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
                              <TableRow key={trigger.id}>
                                <TableCell className="font-medium">{trigger.trigger_type}</TableCell>
                                <TableCell className="max-w-xs truncate">{getTriggerDetails(trigger)}</TableCell>
                                <TableCell>
                                  <Badge variant={trigger.active ? 'default' : 'secondary'}>
                                    {trigger.active ? 'Active' : 'Disabled'}
                                  </Badge>
                                </TableCell>
                                <TableCell>{getLastRun(trigger)}</TableCell>
                                <TableCell>{getNextRun(trigger)}</TableCell>
                                <TableCell className="text-right">
                                  <div className="flex justify-end gap-2">
                                    <Button
                                      variant="ghost"
                                      size="sm"
                                      onClick={() => handleEditTrigger(trigger)}
                                    >
                                      <Edit className="w-4 h-4" />
                                    </Button>
                                    <Button
                                      variant="ghost"
                                      size="sm"
                                      onClick={() => handleDeleteTrigger(trigger.id)}
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
                      <Button size="sm" variant="outline">
                        <Plus className="w-4 h-4 mr-2" />
                        Add Tool
                      </Button>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <div className="grid gap-3 sm:grid-cols-2">
                      {mockTools.map((tool) => (
                        <div
                          key={tool.id}
                          className="flex items-start justify-between gap-3 rounded-lg border p-4 hover:bg-muted/50 transition-colors"
                        >
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-1">
                              <h4 className="font-medium text-sm">{tool.name}</h4>
                              <Badge variant="outline" className="text-xs shrink-0">
                                {tool.category}
                              </Badge>
                            </div>
                            <p className="text-xs text-muted-foreground">{tool.description}</p>
                          </div>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => toast.info(`Removing ${tool.name}`)}
                          >
                            <Trash2 className="w-4 h-4" />
                          </Button>
                        </div>
                      ))}
                    </div>
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
                      <Button size="sm" variant="outline">
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
                              variant="ghost"
                              size="sm"
                              onClick={() => toast.info(mcp.status === 'connected' ? `Disabling ${mcp.name}` : `Enabling ${mcp.name}`)}
                            >
                              <Switch checked={mcp.status === 'connected'} className="pointer-events-none" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => toast.info(`Removing ${mcp.name}`)}
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
      <Dialog open={showTriggerModal} onOpenChange={setShowTriggerModal}>
        <DialogContent className="sm:max-w-[600px]">
          <DialogHeader>
            <DialogTitle>Configure Trigger</DialogTitle>
            <DialogDescription>
              {editingTrigger ? 'Edit trigger configuration' : 'Add a new trigger to this agent'}
            </DialogDescription>
          </DialogHeader>
          <Form {...triggerForm}>
            <form onSubmit={triggerForm.handleSubmit(handleSaveTrigger)} className="space-y-4">
              <FormField
                control={triggerForm.control}
                name="trigger_type"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Trigger Type</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {triggerTypes.map((type) => (
                          <SelectItem key={type} value={type}>
                            {type}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={triggerForm.control}
                name="active"
                render={({ field }) => (
                  <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                    <div className="space-y-0.5">
                      <FormLabel className="text-base">Active</FormLabel>
                      <FormDescription>Enable this trigger</FormDescription>
                    </div>
                    <FormControl>
                      <Switch checked={field.value} onCheckedChange={field.onChange} />
                    </FormControl>
                  </FormItem>
                )}
              />

              {/* Schedule Fields */}
              {watchTriggerType === 'Schedule' && (
                <div className="grid gap-4 sm:grid-cols-2">
                  <FormField
                    control={triggerForm.control}
                    name="schedule_interval"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Interval</FormLabel>
                        <Select onValueChange={field.onChange} value={field.value}>
                          <FormControl>
                            <SelectTrigger>
                              <SelectValue placeholder="Select interval" />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            {scheduledIntervals.map((interval) => (
                              <SelectItem key={interval} value={interval}>
                                {interval}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={triggerForm.control}
                    name="interval_count"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Count</FormLabel>
                        <FormControl>
                          <Input
                            type="number"
                            min={1}
                            {...field}
                            onChange={(e) => field.onChange(parseInt(e.target.value))}
                          />
                        </FormControl>
                        <FormDescription>Run every n intervals</FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>
              )}

              {/* Doc Event Fields */}
              {watchTriggerType === 'Doc Event' && (
                <div className="space-y-4">
                  <div className="grid gap-4 sm:grid-cols-2">
                    <FormField
                      control={triggerForm.control}
                      name="reference_doctype"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>DocType</FormLabel>
                          <FormControl>
                            <Input placeholder="e.g., Sales Invoice" {...field} />
                          </FormControl>
                          <FormDescription>Target document type</FormDescription>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    <FormField
                      control={triggerForm.control}
                      name="doc_event"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Event</FormLabel>
                          <Select onValueChange={field.onChange} value={field.value}>
                            <FormControl>
                              <SelectTrigger>
                                <SelectValue placeholder="Select event" />
                              </SelectTrigger>
                            </FormControl>
                            <SelectContent>
                              {docEvents.map((event) => (
                                <SelectItem key={event} value={event}>
                                  {event}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>

                  <FormField
                    control={triggerForm.control}
                    name="condition"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Condition (Python)</FormLabel>
                        <FormControl>
                          <Textarea
                            placeholder="Use 'doc' to reference the document"
                            className="font-mono resize-y min-h-[100px]"
                            {...field}
                          />
                        </FormControl>
                        <FormDescription>
                          Optional condition to filter events
                        </FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>
              )}

              {/* Webhook Fields */}
              {watchTriggerType === 'Webhook' && (
                <div className="space-y-2">
                  <Label>Webhook URL</Label>
                  <div className="flex gap-2">
                    <Input
                      value={editingTrigger?.webhook_url || `https://api.hufai.com/agent/${id}/webhook/${Date.now()}`}
                      readOnly
                      className="flex-1 font-mono text-sm"
                    />
                    <Button
                      type="button"
                      variant="outline"
                      size="icon"
                      onClick={() => {
                        const url = editingTrigger?.webhook_url || '';
                        navigator.clipboard.writeText(url);
                        toast.success('URL copied');
                      }}
                    >
                      <Copy className="w-4 h-4" />
                    </Button>
                  </div>
                  <p className="text-sm text-muted-foreground">Auto-generated webhook endpoint</p>
                </div>
              )}

              {/* App Event Fields */}
              {watchTriggerType === 'App Event' && (
                <div className="grid gap-4 sm:grid-cols-2">
                  <FormField
                    control={triggerForm.control}
                    name="app_name"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>App Name</FormLabel>
                        <FormControl>
                          <Input placeholder="e.g., Slack" {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={triggerForm.control}
                    name="event_name"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Event Name</FormLabel>
                        <FormControl>
                          <Input placeholder="e.g., message.posted" {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>
              )}

              {/* Manual Fields */}
              {watchTriggerType === 'Manual' && (
                <div className="rounded-lg border p-4 text-sm text-muted-foreground">
                  Manual trigger can be run from workflows or flows. No configuration required.
                </div>
              )}

              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setShowTriggerModal(false)}>
                  Cancel
                </Button>
                <Button type="submit">
                  {editingTrigger ? 'Update' : 'Add'} Trigger
                </Button>
              </DialogFooter>
            </form>
          </Form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
