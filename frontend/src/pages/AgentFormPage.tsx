import { useEffect, useState, useMemo, useCallback } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Form } from '../components/ui/form';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { toast } from 'sonner';
import { AIProvider, AIModel, AgentToolFunctionRef, type ToolType } from '../types/agent.types';
import { getAgent, updateAgent, createAgent, getAgentTriggers, getAgentTrigger, createAgentTrigger, updateAgentTrigger, getDocTypes, getTriggerTypes, type AgentTriggerListItem, type AgentTriggerDoc, type TriggerTypeOption, deleteAgentTrigger, runAgentTest } from '../services/agentApi';
import { getAgentPrompt } from '../services/agentPromptApi';
import { getProviders, getModels } from '../services/providerApi';
import { getToolTypes, getToolFunction, updateToolFunction, getToolFunctionsByName } from '../services/toolApi';
import type { AgentDoc } from '../types/agent.types';
import type { AgentToolType } from '../types/agent.types';
import { SelectToolsModal, SelectMCPServersModal } from '../components/tools';
import { ToolFormModal } from '../components/tools/ToolFormModal';
import type { ToolFormData } from '../types/toolTemplate.types';
import { TriggerModal } from '../components/agent/TriggerModal';
import { getFrappeErrorMessage } from '../lib/frappe-error';
import { db } from '../lib/frappe-sdk';
import { AgentHeader } from '../components/agent/AgentHeader';
import { GeneralTab } from '../components/agent/GeneralTab';
import { BehaviorTab } from '../components/agent/BehaviorTab';
import { TriggersTab } from '../components/agent/TriggersTab';
import { ToolsTab } from '../components/agent/ToolsTab';
import { AdvancedTab } from '../components/agent/AdvancedTab';
import type { AgentPromptOption } from '../components/agent/PromptTemplateSection';
import { PermissionsTab } from '../components/agent/PermissionsTab';
import { KnowledgeTab } from '../components/agent/KnowledgeTab';
import { AgentKnowledgeModal } from '../components/agent/AgentKnowledgeModal';
import { agentFormSchema, type AgentFormValues } from '../components/agent/types';
import { syncMCPTools, getMCPServer, type MCPServerRef } from '../services/mcpApi';
import type { MCPServerDoc } from '../services/mcpApi';
import type { AgentKnowledgeRow } from '../types/agent.types';
import { createFormSubmitHandler, type TabFieldMapping } from '../utils/formValidation';

type PromptListRow = {
  name: string;
  title?: string | null;
  version?: number | null;
  is_latest?: 0 | 1;
  description?: string | null;
};

type AgentToolRow = {
  tool?: string | null;
};

type AgentMcpServerRow = {
  name?: string | null;
  mcp_server: string;
  server_url?: string | null;
  enabled?: 0 | 1 | boolean;
  tool_count?: number | null;
  server_name?: string | null;
  description?: string | null;
};

type AgentUpdatePayload = Omit<Partial<AgentDoc>, "agent_tool"> & {
  agent_tool: Array<{ tool: string }>;
};

function mapAgentDocToFormValues(agent: Partial<AgentDoc>): AgentFormValues {
  return {
    agent_name: agent.agent_name || '',
    provider: agent.provider || '',
    model: agent.model || '',
    temperature: agent.temperature ?? 1,
    top_p: agent.top_p ?? 1,
    disabled: agent.disabled === 1,
    allow_chat: agent.allow_chat === 1,
    persist_conversation: agent.persist_conversation === 1,
    persist_user_history: agent.persist_user_history === 1,
    enable_multi_run: agent.enable_multi_run === 1,
    description: agent.description || '',
    instructions: agent.instructions || '',
    default_plan: agent.default_plan || [],
    prompt_mode: agent.prompt_mode || 'Local',
    agent_prompt: agent.agent_prompt || '',
    prompt_version_locked: agent.prompt_version_locked === 1,
    template_version_at_attach:
      agent.template_version_at_attach !== undefined ? agent.template_version_at_attach : undefined,
    allow_guest: agent.allow_guest === 1,
    allowed_users: (agent.allowed_users || []).map((row) => row.user).filter(Boolean),
    allowed_roles: (agent.allowed_roles || []).map((row) => row.role).filter(Boolean),
    copied_from_prompt: agent.copied_from_prompt ?? undefined,
    enable_prompt_caching: agent.enable_prompt_caching === 1,
    cache_control_type: agent.cache_control_type || '',
    cache_system_message: agent.cache_system_message === 1,
    cache_conversation_history: agent.cache_conversation_history === 1,
    context_strategy: agent.context_strategy || undefined,
    summary_model: agent.summary_model || undefined,
    summary_ratio: agent.summary_ratio !== undefined && agent.summary_ratio !== null ? agent.summary_ratio : undefined,
    history_limit: agent.history_limit !== undefined && agent.history_limit !== null ? agent.history_limit : undefined,
    max_knowledge_tokens:
      agent.max_knowledge_tokens !== undefined && agent.max_knowledge_tokens !== null ? agent.max_knowledge_tokens : undefined,
    max_turns: agent.max_turns !== undefined && agent.max_turns !== null ? agent.max_turns : undefined,
    enable_conversation_data: agent.enable_conversation_data === 1,
    autonaming_of_conversation_title: agent.autonaming_of_conversation_title === 1,
    agent_color: agent.agent_color?.trim() || '',
    show_tool_execution_details: agent.show_tool_execution_details === 1,
    image_generation_model: agent.image_generation_model || undefined,
    tts_model: agent.tts_model || undefined,
    tts_voice: agent.tts_voice || '',
    stt_model: agent.stt_model || undefined,
  };
}

export function AgentFormPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const isNew = id === 'new';
  const [pendingSelectedPrompt, setPendingSelectedPrompt] = useState<string | null>(null);
  const [pendingSelectedPromptField, setPendingSelectedPromptField] = useState<string | null>(null);
  const [pendingScrollToPromptField, setPendingScrollToPromptField] = useState(false);
  const [resolvingPendingPrompt, setResolvingPendingPrompt] = useState(false);

  // Tab configuration - single source of truth
  const tabConfig = {
    general: {
      label: 'General',
      fields: ['agent_name', 'provider', 'model', 'temperature', 'top_p', 'description', 'instructions', 'enable_prompt_caching', 'cache_control_type', 'cache_system_message', 'cache_conversation_history', 'prompt_mode', 'agent_prompt', 'prompt_version_locked', 'template_version_at_attach'],
      default: true,
      disabled: false,
    },
    behavior: {
      label: 'Behavior',
      fields: ['allow_chat', 'persist_conversation', 'persist_user_history', 'enable_multi_run', 'default_plan'],
      default: false,
      disabled: false,
    },
    triggers: {
      label: 'Triggers',
      fields: [], // Triggers tab doesn't have form fields
      default: false,
      disabled: false,
    },
    tools: {
      label: 'Tools & MCP',
      fields: [],
      default: false,
      disabled: false,
    },
    knowledge: {
      label: 'Knowledge',
      fields: [],
      default: false,
      disabled: false,
    },
    permissions: {
      label: 'Permissions',
      fields: ['allow_guest', 'allowed_users', 'allowed_roles'],
      default: false,
      disabled: false,
    },
    advanced: {
      label: 'Advanced Settings',
      fields: [
       'context_strategy',
        'summary_model',
        'summary_ratio',
        'history_limit',
        'max_knowledge_tokens',
        'max_turns',
        'enable_conversation_data',
        'autonaming_of_conversation_title',
        'agent_color',
        'show_tool_execution_details',
        'image_generation_model',
        'tts_model',
        'tts_voice',
        'stt_model',
      ],
      default: false,
      disabled: false,
    },
  } as const;

  // Extract derived values from tab config (memoized to avoid recreating on every render)
  const validTabs = Object.keys(tabConfig);
  const defaultTab = Object.entries(tabConfig).find(([, config]) => config.default)?.[0] || validTabs[0];
  const tabFieldMapping: TabFieldMapping = Object.fromEntries(
    Object.entries(tabConfig).map(([key, config]) => [key, [...config.fields]])
  );
  const tabLabels = Object.fromEntries(
    Object.entries(tabConfig).map(([key, config]) => [key, config.label])
  );
  
  // State to track active tab from URL hash
  const [activeTab, setActiveTab] = useState<string>(() => {
    const hashFromUrl = window.location.hash.slice(1); // Remove the # symbol
    return (hashFromUrl && validTabs.includes(hashFromUrl)) ? hashFromUrl : defaultTab;
  });

  // Listen for hash changes (back/forward navigation)
  useEffect(() => {
    const handleHashChange = () => {
      const hashFromUrl = window.location.hash.slice(1);
      const tab = (hashFromUrl && validTabs.includes(hashFromUrl)) ? hashFromUrl : defaultTab;
      setActiveTab(tab);
    };

    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, [defaultTab, validTabs]);

  // Handler to update tab in URL hash
  const handleTabChange = (value: string) => {
    setActiveTab(value);
    // Only set hash if it's not the default tab, or clear hash if switching back to default
    if (value === defaultTab) {
      // Clear hash when switching to default tab
      window.history.replaceState(null, '', window.location.pathname);
    } else {
      // Set hash for non-default tabs
      window.location.hash = value;
    }
  };
  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);
  const [deletingTrigger, setDeletingTrigger] = useState(false);
  const [providers, setProviders] = useState<AIProvider[]>([]);
  const [models, setModels] = useState<AIModel[]>([]);
  const [allModels, setAllModels] = useState<AIModel[]>([]);
  const [promptOptions, setPromptOptions] = useState<AgentPromptOption[]>([]);
  const [loadingPrompts, setLoadingPrompts] = useState(false);
  const [triggers, setTriggers] = useState<AgentTriggerListItem[]>([]);
  const [showTriggerModal, setShowTriggerModal] = useState(false);
  const [editingTrigger, setEditingTrigger] = useState<AgentTriggerDoc | null>(null);
  const [triggerFilter, setTriggerFilter] = useState<string>('all');
  const [triggerStatusFilter, setTriggerStatusFilter] = useState<string>('all');
  const [optimizingPrompt, setOptimizingPrompt] = useState(false);
  const [showToolsModal, setShowToolsModal] = useState(false);
  const [showToolFormModal, setShowToolFormModal] = useState(false);
  const [editingToolId, setEditingToolId] = useState<string | null>(null);
  const [selectedTools, setSelectedTools] = useState<AgentToolFunctionRef[]>([]);
  const [initialTools, setInitialTools] = useState<AgentToolFunctionRef[]>([]); // Track initial tools state
  const [toolTypes, setToolTypes] = useState<AgentToolType[]>([]);
  const [initialDisabled, setInitialDisabled] = useState(false); // Track initial disabled state
  const [docTypes, setDocTypes] = useState<Array<{ name: string }>>([]);
  const [loadingDocTypes, setLoadingDocTypes] = useState(false);
  const [triggerTypes, setTriggerTypes] = useState<TriggerTypeOption[]>([]);
  const [loadingTriggerTypes, setLoadingTriggerTypes] = useState(false);
  const [showMCPServersModal, setShowMCPServersModal] = useState(false);
  const [mcpServers, setMcpServers] = useState<MCPServerRef[]>([]);
  const [initialMcpServers, setInitialMcpServers] = useState<MCPServerRef[]>([]); // Track initial MCP servers state
  const [mcpLoading, setMcpLoading] = useState(false);
  const [knowledgeSources, setKnowledgeSources] = useState<AgentKnowledgeRow[]>([]);
  const [initialKnowledgeSources, setInitialKnowledgeSources] = useState<AgentKnowledgeRow[]>([]);
  const [agentStats, setAgentStats] = useState<{ last_run?: string | null; total_run?: number | null }>({});
  const [showKnowledgeModal, setShowKnowledgeModal] = useState(false);
  const [editingKnowledgeIndex, setEditingKnowledgeIndex] = useState<number | null>(null);
  const [allowChat, setAllowChat] = useState(false); // Persisted value only – updated on load/save
  const [users, setUsers] = useState<Array<{ name: string }>>([]);
  const [roles, setRoles] = useState<Array<{ name: string }>>([]);
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
        default_plan: [],
        prompt_mode: "Local",
        agent_prompt: '',
        prompt_version_locked: false,
        template_version_at_attach: undefined,
        allow_guest: false,
        allowed_users: [],
        allowed_roles: [],
        enable_prompt_caching: false,
        cache_control_type: "",
        cache_system_message: false,
        cache_conversation_history:false,
        context_strategy: undefined,
        summary_model: undefined,
        summary_ratio: undefined,
        history_limit: undefined,
        max_knowledge_tokens: undefined,
        max_turns: undefined,
        enable_conversation_data: false,
        autonaming_of_conversation_title: false,
        agent_color: '',
        show_tool_execution_details: false,
        image_generation_model: undefined,
        tts_model: undefined,
        tts_voice: '',
        stt_model: undefined,
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

  // Check if MCP servers have changed by comparing server names and enabled states
  const mcpServersChanged = useMemo(() => {
    if (isNew) return mcpServers.length > 0; // New agent with MCP servers selected

    // Normalize enabled state to number for comparison
    const normalizeEnabled = (enabled: boolean | number | undefined): number => {
      return enabled === true || enabled === 1 ? 1 : 0;
    };

    // Compare by mcp_server link field (the actual server name) and enabled state
    const initialServerMap = new Map(
      initialMcpServers.map((s) => [`${s.mcp_server}:${normalizeEnabled(s.enabled)}`, s])
    );
    const currentServerMap = new Map(
      mcpServers.map((s) => [`${s.mcp_server}:${normalizeEnabled(s.enabled)}`, s])
    );

    if (initialServerMap.size !== currentServerMap.size) return true;

    for (const [key] of currentServerMap) {
      if (!initialServerMap.has(key)) return true;
    }

    return false;
  }, [mcpServers, initialMcpServers, isNew]);

  const knowledgeChanged = useMemo(() => {
    if (isNew) return knowledgeSources.length > 0;
    if (knowledgeSources.length !== initialKnowledgeSources.length) return true;
    return knowledgeSources.some((ks, i) => {
      const init = initialKnowledgeSources[i];
      return (
        ks.knowledge_source !== init.knowledge_source ||
        ks.mode !== init.mode ||
        ks.priority !== init.priority ||
        ks.max_chunks !== init.max_chunks ||
        ks.token_budget !== init.token_budget ||
        (ks.description || '') !== (init.description || '')
      );
    });
  }, [knowledgeSources, initialKnowledgeSources, isNew]);

  const showSaveButton = isNew || isDirty || toolsChanged || disabledChanged || mcpServersChanged || knowledgeChanged;

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
      db.getDocList('User', { fields: ['name'], limit: 1000, orderBy: { field: 'name', order: 'asc' } }),
      db.getDocList('Role', { fields: ['name'], limit: 1000, orderBy: { field: 'name', order: 'asc' } }),
    ]).then(([providersData, modelsData, toolTypesData, usersData, rolesData]) => {
      setProviders(providersData as AIProvider[]);
      setAllModels(modelsData);
      setToolTypes(toolTypesData);
      setUsers(usersData as Array<{ name: string }>);
      setRoles((rolesData as Array<{ name: string }>).filter((role) => role.name !== 'Guest'));
    }).catch((error) => {
      console.error('Error loading providers/models/types:', error);
      toast.error('Failed to load providers and models');
    });
  }, []);

  useEffect(() => {
    let cancelled = false;

    const loadPromptOptions = async () => {
      setLoadingPrompts(true);
      try {
        const prompts = await db.getDocList('Agent Prompt', {
          fields: ['name', 'title', 'version', 'is_latest', 'description'],
          filters: [['is_active', '=', 1]],
          limit: 500,
          orderBy: { field: 'modified', order: 'desc' },
        }) as PromptListRow[];

        if (cancelled) {
          return;
        }

        setPromptOptions(
          prompts.map((prompt) => ({
            value: prompt.name,
            label: prompt.title || prompt.name,
            description: prompt.description || undefined,
            version: typeof prompt.version === 'number' ? prompt.version : undefined,
            isLatest: prompt.is_latest === 1,
          }))
        );
      } catch (error) {
        console.error('Error loading prompt templates:', error);
        if (!cancelled) {
          setPromptOptions([]);
          toast.error('Failed to load Agent Prompt templates');
        }
      } finally {
        if (!cancelled) {
          setLoadingPrompts(false);
        }
      }
    };

    loadPromptOptions();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const state = location.state as { selectedPrompt?: string; showTab?: string; selectedPromptField?: string } | null;
    if (state?.selectedPrompt) {
      setPendingSelectedPrompt(state.selectedPrompt);
      setPendingSelectedPromptField(state.selectedPromptField || 'agent_prompt');
      if (state.showTab) {
        setActiveTab(state.showTab);
      }
    }
  }, [location.state]);

  useEffect(() => {
    if (!pendingSelectedPrompt) return;
    if (resolvingPendingPrompt) return;

    const fieldName = pendingSelectedPromptField || 'agent_prompt';
    let cancelled = false;

    const run = async () => {
      setResolvingPendingPrompt(true);
      try {
        const promptExists = promptOptions.some((option) => option.value === pendingSelectedPrompt);

        // Ensure the selector's option list contains the newly created prompt.
        if (!promptExists) {
          const promptDoc = await getAgentPrompt(pendingSelectedPrompt);

          if (promptDoc?.is_active === 1) {
            const option: AgentPromptOption = {
              value: promptDoc.name,
              label: promptDoc.title || promptDoc.name,
              description: promptDoc.description || undefined,
              version: typeof promptDoc.version === 'number' ? promptDoc.version : undefined,
              isLatest: promptDoc.is_latest === 1,
            };

            setPromptOptions((prev) => {
              if (prev.some((p) => p.value === option.value)) return prev;
              return [option, ...prev];
            });
          }
        }

        // If we're coming back in Local mode, switch to Template so the selector is visible.
        if (fieldName === 'agent_prompt' && form.getValues('prompt_mode') !== 'Template') {
          form.setValue('prompt_mode', 'Template', { shouldDirty: true });
        }

        // Attach/select the created prompt in the form.
        form.setValue(fieldName as any, pendingSelectedPrompt as any, { shouldDirty: true });

        setPendingSelectedPrompt(null);
        setPendingSelectedPromptField(null);

        if (fieldName === 'agent_prompt') {
          setPendingScrollToPromptField(true);
        }

        // clear transient history state so we don't re-run this on future navigations
        navigate(`${location.pathname}${location.search}${location.hash}`, { replace: true, state: {} });
      } catch (error) {
        console.error('Failed to resolve pending prompt selection:', error);
        toast.error('Failed to select newly created prompt');
      } finally {
        if (!cancelled) setResolvingPendingPrompt(false);
      }
    };

    run();

    return () => {
      cancelled = true;
    };
  }, [
    pendingSelectedPrompt,
    pendingSelectedPromptField,
    resolvingPendingPrompt,
    promptOptions,
    form,
    location.pathname,
    location.search,
    location.hash,
    navigate,
  ]);

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

  const watchPromptMode = form.watch('prompt_mode');
  const watchAgentPrompt = form.watch('agent_prompt');

  useEffect(() => {
    // Don't clear prompt selection while we're applying an incoming selection from navigation.
    if (pendingSelectedPrompt) return;
    if (watchPromptMode === 'Local') {
      form.setValue('agent_prompt', '', { shouldDirty: false });
      form.setValue('prompt_version_locked', false, { shouldDirty: false });
      form.setValue('template_version_at_attach', undefined, { shouldDirty: false });
      return;
    }

    if (watchPromptMode === 'Template' && !watchAgentPrompt) {
      form.setValue('prompt_version_locked', false, { shouldDirty: false });
      form.setValue('template_version_at_attach', undefined, { shouldDirty: false });
    }
  }, [watchPromptMode, watchAgentPrompt, form, pendingSelectedPrompt]);

  useEffect(() => {
    if (watchPromptMode !== 'Template' || !watchAgentPrompt) {
      return;
    }

    const selectedPrompt = promptOptions.find((option) => option.value === watchAgentPrompt);
    if (!selectedPrompt || typeof selectedPrompt.version !== 'number') {
      return;
    }

    const currentVersion = form.getValues('template_version_at_attach');
    if (currentVersion === selectedPrompt.version) {
      return;
    }

    form.setValue('template_version_at_attach', selectedPrompt.version, { shouldDirty: true });
  }, [watchPromptMode, watchAgentPrompt, promptOptions, form]);

  useEffect(() => {
    if (!pendingScrollToPromptField) return;
    if (activeTab !== 'general') return;
    if (watchPromptMode !== 'Template') return;

    const el = document.getElementById('agent-prompt-field');
    if (el) {
      // Wait a couple frames for the tab content to finish rendering.
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        });
      });
    }

    setPendingScrollToPromptField(false);
  }, [pendingScrollToPromptField, activeTab, watchPromptMode]);

  // Load agent data when id is available (only for edit mode)
  useEffect(() => {
    if (id && !isNew) {
      getAgent(id).then((data: AgentDoc) => {
        // Resolved merge conflict: prefer using the utility function when available, fallback to explicit mapping if not.
        if (typeof mapAgentDocToFormValues === 'function') {
          form.reset(mapAgentDocToFormValues(data));
        } else {
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
            default_plan: data.default_plan || [],
            prompt_mode: data.prompt_mode || 'Local',
            agent_prompt: data.agent_prompt || '',
            prompt_version_locked: data.prompt_version_locked === 1,
            template_version_at_attach: data.template_version_at_attach !== undefined ? data.template_version_at_attach : undefined,
            allow_guest: data.allow_guest === 1,
            allowed_users: (data.allowed_users || []).map((row) => row.user).filter(Boolean),
            allowed_roles: (data.allowed_roles || []).map((row) => row.role).filter(Boolean),
            enable_prompt_caching: data.enable_prompt_caching === 1,
            cache_control_type: data.cache_control_type || '',
            cache_system_message: data.cache_system_message === 1,
            cache_conversation_history: data.cache_conversation_history === 1,
            context_strategy: data.context_strategy || undefined,
            summary_model: data.summary_model || undefined,
            summary_ratio: data.summary_ratio !== undefined && data.summary_ratio !== null ? data.summary_ratio : undefined,
            history_limit: data.history_limit !== undefined && data.history_limit !== null ? data.history_limit : undefined,
            max_knowledge_tokens: data.max_knowledge_tokens !== undefined && data.max_knowledge_tokens !== null ? data.max_knowledge_tokens : undefined,
            max_turns: data.max_turns !== undefined && data.max_turns !== null ? data.max_turns : undefined,
            enable_conversation_data: data.enable_conversation_data === 1,
            autonaming_of_conversation_title: data.autonaming_of_conversation_title === 1,
            agent_color: data.agent_color?.trim() || '',
            show_tool_execution_details: data.show_tool_execution_details === 1,
  
            image_generation_model: data.image_generation_model || undefined,
            tts_model: data.tts_model || undefined,
            tts_voice: data.tts_voice || '',
            stt_model: data.stt_model || undefined,
          });
        }
        // Track initial disabled state and persisted allow_chat
        setInitialDisabled(data.disabled === 1);
        setAllowChat(data.allow_chat === 1);
        setAgentStats({ last_run: data.last_run ?? null, total_run: data.total_run ?? null });
        // Load tools from agent_tool field
        // agent_tool is a child table with format: [{ tool: "tool-name" }, ...]
        if (data.agent_tool && Array.isArray(data.agent_tool) && data.agent_tool.length > 0) {
          // Fetch full tool details for each tool reference
          const toolNames = (data.agent_tool as AgentToolRow[]).map((item) => item.tool).filter(Boolean) as string[];
          if (toolNames.length > 0) {
            getToolFunctionsByName(toolNames)
              .then((tools) => {
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
        // Load MCP servers from agent_mcp_server child table (already in agent document)
        if (data.agent_mcp_server && Array.isArray(data.agent_mcp_server) && data.agent_mcp_server.length > 0) {
          // First, map child table data to MCPServerRef format
          const childTableServers: MCPServerRef[] = (data.agent_mcp_server as AgentMcpServerRow[]).map((item) => ({
            name: item.name || '', // Child table row name
            mcp_server: item.mcp_server, // Link to MCP Server DocType
            server_url: item.server_url || '',
            enabled: item.enabled === 1 || item.enabled === true ? 1 : 0,
            tool_count: item.tool_count || 0,
            server_name: item.server_name ?? undefined, // May be included from Frappe's serialization
            description: item.description ?? undefined, // May be included from Frappe's serialization
          }));

          // Fetch MCP Server documents to get the enabled status and other details
          Promise.all(
            childTableServers.map(async (server) => {
              try {
                const mcpServerDoc = await getMCPServer(server.mcp_server);
                return {
                  ...server,
                  server_name: mcpServerDoc.server_name || server.server_name || server.mcp_server,
                  description: mcpServerDoc.description || server.description,
                  mcp_enabled: mcpServerDoc.enabled === 1 ? 1 : 0, // Enabled status from MCP Server DocType
                  server_url: mcpServerDoc.server_url || server.server_url,
                };
              } catch (error) {
                console.error(`Error fetching MCP Server ${server.mcp_server}:`, error);
                // If fetch fails, keep the server data but mark mcp_enabled as undefined
                return {
                  ...server,
                  mcp_enabled: undefined,
                };
              }
            })
          ).then((enrichedServers) => {
            setMcpServers(enrichedServers);
            setInitialMcpServers(enrichedServers);
          });
        } else {
          setMcpServers([]);
          setInitialMcpServers([]);
        }
        // Load knowledge sources from agent_knowledge child table
        if (data.agent_knowledge && Array.isArray(data.agent_knowledge) && data.agent_knowledge.length > 0) {
          const ksRows: AgentKnowledgeRow[] = data.agent_knowledge.map((item) => ({
            name: item.name,
            knowledge_source: item.knowledge_source,
            mode: item.mode || 'Optional',
            priority: item.priority ?? 0,
            max_chunks: item.max_chunks ?? 5,
            token_budget: item.token_budget ?? 2000,
            description: item.description || undefined,
          }));
          setKnowledgeSources(ksRows);
          setInitialKnowledgeSources(ksRows);
        } else {
          setKnowledgeSources([]);
          setInitialKnowledgeSources([]);
        }
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
      setMcpServers([]);
      setInitialMcpServers([]);
      setKnowledgeSources([]);
      setInitialKnowledgeSources([]);
      setAgentStats({});
      setLoading(false);
    }
  }, [id, isNew, form]);

  const onSubmit = useCallback(async (values: AgentFormValues) => {
    setSaving(true);
    try {
      // Convert form values (booleans) to AgentDoc format (numbers 0/1)
      const agentData: AgentUpdatePayload = {
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
        default_plan: values.default_plan || [],
        prompt_mode: values.prompt_mode || 'Local',
        agent_prompt: values.agent_prompt || '',
        prompt_version_locked: values.prompt_version_locked ? 1 : 0,
        template_version_at_attach: values.template_version_at_attach !== undefined ? values.template_version_at_attach : undefined,
        allow_guest: values.allow_guest ? 1 : 0,
        allowed_users: (values.allowed_users || []).map((user) => ({ user })) as any,
        allowed_roles: (values.allowed_roles || []).map((role) => ({ role })) as any,
        enable_prompt_caching: values.enable_prompt_caching ? 1 : 0,
        cache_control_type: values.cache_control_type || '',
        cache_system_message: values.cache_system_message ? 1 : 0,
        cache_conversation_history: values.cache_conversation_history ? 1 : 0,
        context_strategy: values.context_strategy || undefined,
        summary_model: values.summary_model || undefined,
        summary_ratio: values.summary_ratio !== undefined ? values.summary_ratio : undefined,
        history_limit: values.history_limit !== undefined ? values.history_limit : undefined,
        max_knowledge_tokens: values.max_knowledge_tokens !== undefined ? values.max_knowledge_tokens : undefined,
        max_turns: values.max_turns !== undefined ? values.max_turns : undefined,
        enable_conversation_data: values.enable_conversation_data ? 1 : 0,
        autonaming_of_conversation_title: values.autonaming_of_conversation_title ? 1 : 0,
        agent_color: values.agent_color?.trim() || undefined,
        show_tool_execution_details: values.show_tool_execution_details ? 1 : 0,

        image_generation_model: values.image_generation_model || undefined,
        tts_model: values.tts_model || undefined,
        tts_voice: values.tts_voice || undefined,
        stt_model: values.stt_model || undefined,
        // Include tools - Frappe child table format: array of objects with 'tool' field pointing to Agent Tool Function name
        agent_tool: selectedTools.map((tool) => ({
          tool: tool.name,
        })),
        // Include MCP servers - Frappe child table format: array of objects with 'mcp_server' field and 'enabled' field
        agent_mcp_server: mcpServers.map((server) => ({
          mcp_server: server.mcp_server,
          enabled: (server.enabled === true || server.enabled === 1) ? 1 : (0 as 0 | 1),
        })),
        agent_knowledge: knowledgeSources.map((ks) => ({
          ...(ks.name ? { name: ks.name } : {}),
          knowledge_source: ks.knowledge_source,
          mode: ks.mode,
          priority: ks.priority,
          max_chunks: ks.max_chunks,
          token_budget: ks.token_budget,
          description: ks.description || '',
        })),
      } as any;

      if (isNew) {
        // Create new agent
        const newAgent = await createAgent(agentData as unknown as Partial<AgentDoc>);
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
          default_plan: newAgent.default_plan || [],
          prompt_mode: newAgent.prompt_mode || 'Local',
          agent_prompt: newAgent.agent_prompt || '',
          prompt_version_locked: newAgent.prompt_version_locked === 1,
          template_version_at_attach: newAgent.template_version_at_attach !== undefined ? newAgent.template_version_at_attach : undefined,
          allow_guest: newAgent.allow_guest === 1,
          allowed_users: (newAgent.allowed_users || []).map((row) => row.user).filter(Boolean),
          allowed_roles: (newAgent.allowed_roles || []).map((row) => row.role).filter(Boolean),
          enable_prompt_caching: newAgent.enable_prompt_caching === 1,
          cache_control_type: newAgent.cache_control_type || '',
          cache_system_message: newAgent.cache_system_message === 1,
          cache_conversation_history: newAgent.cache_conversation_history === 1,
          context_strategy: newAgent.context_strategy || undefined,
          summary_model: newAgent.summary_model || undefined,
          summary_ratio: newAgent.summary_ratio !== undefined && newAgent.summary_ratio !== null ? newAgent.summary_ratio : undefined,
          history_limit: newAgent.history_limit !== undefined && newAgent.history_limit !== null ? newAgent.history_limit : undefined,
          max_knowledge_tokens: newAgent.max_knowledge_tokens !== undefined && newAgent.max_knowledge_tokens !== null ? newAgent.max_knowledge_tokens : undefined,
          max_turns: newAgent.max_turns !== undefined && newAgent.max_turns !== null ? newAgent.max_turns : undefined,
          enable_conversation_data: newAgent.enable_conversation_data === 1,
          autonaming_of_conversation_title: newAgent.autonaming_of_conversation_title === 1,
          agent_color: newAgent.agent_color?.trim() || '',
          show_tool_execution_details: newAgent.show_tool_execution_details === 1,

          image_generation_model: newAgent.image_generation_model || undefined,
          tts_model: newAgent.tts_model || undefined,
          tts_voice: newAgent.tts_voice || '',
          stt_model: newAgent.stt_model || undefined,
        });
        setInitialDisabled(newAgent.disabled === 1);
        setAllowChat(newAgent.allow_chat === 1);
        setInitialKnowledgeSources([...knowledgeSources]);
        setAgentStats({ last_run: newAgent.last_run ?? null, total_run: newAgent.total_run ?? null });
        // Navigate to the edit page with the new agent's ID
        navigate(`/agents/${newAgent.name}`);
      } else if (id) {
        // Update existing agent
        await updateAgent(id, agentData as unknown as Partial<AgentDoc>);
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
  default_plan: values.default_plan || [],
  prompt_mode: values.prompt_mode,
  agent_prompt: values.agent_prompt,
  prompt_version_locked: values.prompt_version_locked,
  template_version_at_attach: values.template_version_at_attach,
  allow_guest: values.allow_guest,
  allowed_users: values.allowed_users || [],
  allowed_roles: values.allowed_roles || [],
  enable_prompt_caching: values.enable_prompt_caching,
  cache_control_type: values.cache_control_type,
  cache_system_message: values.cache_system_message,
  cache_conversation_history: values.cache_conversation_history,
  context_strategy: values.context_strategy,
  summary_model: values.summary_model,
  summary_ratio: values.summary_ratio,
  history_limit: values.history_limit,
  max_knowledge_tokens: values.max_knowledge_tokens,
  max_turns: values.max_turns,
  enable_conversation_data: values.enable_conversation_data,
  autonaming_of_conversation_title: values.autonaming_of_conversation_title,
  agent_color: values.agent_color,
  show_tool_execution_details: values.show_tool_execution_details,

  image_generation_model: values.image_generation_model,
  tts_model: values.tts_model,
  tts_voice: values.tts_voice,
  stt_model: values.stt_model,
});
// Reset tools, disabled state, and persisted allow_chat after successful update
setInitialTools([...selectedTools]);
setInitialDisabled(values.disabled);
setAllowChat(values.allow_chat);
        if (id) {
          getAgent(id).then((updatedData: AgentDoc) => {
            form.reset(mapAgentDocToFormValues(updatedData));
            setAgentStats({
              last_run: updatedData.last_run ?? null,
              total_run: updatedData.total_run ?? null,
            });
            // Reset tools, disabled state, and persisted allow_chat after successful update
            setInitialTools([...selectedTools]);
            setInitialDisabled(updatedData.disabled === 1);
            setAllowChat(updatedData.allow_chat === 1);
            // Reload MCP servers from updated agent document
            if (updatedData.agent_mcp_server && Array.isArray(updatedData.agent_mcp_server) && updatedData.agent_mcp_server.length > 0) {
              const childTableServers: MCPServerRef[] = (updatedData.agent_mcp_server as AgentMcpServerRow[]).map((item) => ({
                name: item.name || '',
                mcp_server: item.mcp_server,
                server_url: item.server_url || '',
                enabled: item.enabled === 1 || item.enabled === true ? 1 : 0,
                tool_count: item.tool_count || 0,
                server_name: item.server_name ?? undefined,
                description: item.description ?? undefined,
              }));

              // Fetch MCP Server documents to get the enabled status
              Promise.all(
                childTableServers.map(async (server) => {
                  try {
                    const mcpServerDoc = await getMCPServer(server.mcp_server);
                    return {
                      ...server,
                      server_name: mcpServerDoc.server_name || server.server_name || server.mcp_server,
                      description: mcpServerDoc.description || server.description,
                      mcp_enabled: mcpServerDoc.enabled === 1 ? 1 : 0,
                      server_url: mcpServerDoc.server_url || server.server_url,
                    };
                  } catch (error) {
                    console.error(`Error fetching MCP Server ${server.mcp_server}:`, error);
                    return {
                      ...server,
                      mcp_enabled: undefined,
                    };
                  }
                })
              ).then((enrichedServers) => {
                setMcpServers(enrichedServers);
                setInitialMcpServers(enrichedServers);
              });
            } else {
              setMcpServers([]);
              setInitialMcpServers([]);
            }
            // Reload knowledge sources from updated agent document
            if (updatedData.agent_knowledge && Array.isArray(updatedData.agent_knowledge) && updatedData.agent_knowledge.length > 0) {
              const ksRows: AgentKnowledgeRow[] = updatedData.agent_knowledge.map((item) => ({
                name: item.name,
                knowledge_source: item.knowledge_source,
                mode: item.mode || 'Optional',
                priority: item.priority ?? 0,
                max_chunks: item.max_chunks ?? 5,
                token_budget: item.token_budget ?? 2000,
                description: item.description || undefined,
              }));
              setKnowledgeSources(ksRows);
              setInitialKnowledgeSources(ksRows);
            } else {
              setKnowledgeSources([]);
              setInitialKnowledgeSources([]);
            }
          }).catch((error) => {
            console.error('Error reloading agent:', error);
          });
        }
      }
    } catch (error) {
      console.error(`Error ${isNew ? 'creating' : 'updating'} agent:`, error);
      const errorMessage = getFrappeErrorMessage(error);
      toast.error(errorMessage || `Failed to ${isNew ? 'create' : 'update'} agent. Please try again.`);
    } finally {
      setSaving(false);
    }
  }, [form, id, isNew, mcpServers, navigate, selectedTools, knowledgeSources]);

  // Memoize the form submit handler to avoid recreating it on every render
  const handleFormSubmit = useMemo(
    () => createFormSubmitHandler(form, activeTab, tabFieldMapping, tabLabels, onSubmit),
    [form, activeTab, tabFieldMapping, tabLabels, onSubmit]
  );

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

  const [toolFormData, setToolFormData] = useState<Partial<ToolFormData> | null>(null);
  const [loadingToolData, setLoadingToolData] = useState(false);

  const handleEditTool = async (toolId: string) => {
    setEditingToolId(toolId);
    setLoadingToolData(true);
    try {
      const tool = await getToolFunction(toolId);
      if (tool) {
        // Convert tool data to form format
        setToolFormData({
          tool_name: tool.tool_name,
          tool_type: tool.tool_type,
          types: tool.types as ToolType,
          description: tool.description,
          reference_doctype: tool.reference_doctype,
          agent: tool.agent,
          function_path: tool.function_path,
          function_name: tool.function_name,
          pass_parameters_as_json: tool.pass_parameters_as_json === 1,
          provider_app: tool.provider_app,
          base_url: tool.base_url,
          required_permission: tool.required_permission,
          is_read_only: tool.is_read_only === 1,
          allowed_for_guest: tool.allowed_for_guest === 1,
          parameters: tool.parameters || [],
          http_headers: tool.http_headers || [],
        });
        setShowToolFormModal(true);
      }
    } catch (error) {
      console.error('Error loading tool:', error);
      const errorMessage = getFrappeErrorMessage(error);
      toast.error(errorMessage || 'Failed to load tool');
    } finally {
      setLoadingToolData(false);
    }
  };

  const handleToolFormSubmit = async (data: ToolFormData) => {
    if (!editingToolId) return;
    
    try {
      // Update existing tool
      await updateToolFunction(editingToolId, {
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

      // Update the tool in the selected tools list
      setSelectedTools(selectedTools.map((t) =>
        t.name === editingToolId
          ? { ...t, tool_name: data.tool_name, description: data.description, tool_type: data.tool_type }
          : t
      ));
      toast.success('Tool updated successfully!');
      setShowToolFormModal(false);
      setEditingToolId(null);
      setToolFormData(null);
    } catch (error) {
      console.error('Error saving tool:', error);
      const errorMessage = getFrappeErrorMessage(error);
      toast.error(errorMessage || 'Failed to save tool');
    }
  };

  const handleAddMCPServers = (servers: MCPServerDoc[]) => {
    // Convert MCPServerDoc to MCPServerRef format for child table
    const newServers: MCPServerRef[] = servers.map((server) => ({
      name: '', // Will be set by Frappe when saved
      mcp_server: server.name,
      server_name: server.server_name,
      description: server.description,
      server_url: server.server_url,
      enabled: true, // Default to enabled when adding
      mcp_enabled: server.enabled === 1,
      tool_count: 0, // Will be updated when synced
    }));
    setMcpServers([...mcpServers, ...newServers]);
  };

  const handleRemoveMCPServer = (serverId: string) => {
    setMcpServers(mcpServers.filter((s) => s.name !== serverId));
    toast.success('MCP server removed');
  };

  const handleToggleMCPServer = async (serverId: string, enabled: boolean) => {
    setMcpServers(
      mcpServers.map((s) =>
        s.name === serverId ? { ...s, enabled } : s
      )
    );
    toast.success(`MCP server ${enabled ? 'enabled' : 'disabled'}`);
  };

  const handleSyncMCPServer = async (serverId: string) => {
    const server = mcpServers.find((s) => s.name === serverId);
    if (!server) {
      toast.error('MCP server not found');
      return;
    }

    setMcpLoading(true);
    try {
      const result = await syncMCPTools(server.mcp_server);
      if (result.success) {
        // Update the server with new tool count
        setMcpServers(
          mcpServers.map((s) =>
            s.name === serverId
              ? {
                  ...s,
                  tool_count: result.tool_count ?? s.tool_count,
                  last_sync: new Date().toISOString(),
                }
              : s
          )
        );
        toast.success(
          `Synced ${result.tool_count ?? 0} tool${(result.tool_count ?? 0) !== 1 ? 's' : ''} from MCP server`
        );
      } else {
        toast.error(result.error || 'Failed to sync MCP server tools');
      }
    } catch (error) {
      console.error('Error syncing MCP server:', error);
      const errorMessage = getFrappeErrorMessage(error);
      toast.error(errorMessage || 'Failed to sync MCP server tools');
    } finally {
      setMcpLoading(false);
    }
  };

  const handleAddKnowledge = () => {
    setEditingKnowledgeIndex(null);
    setShowKnowledgeModal(true);
  };

  const handleEditKnowledge = (index: number) => {
    setEditingKnowledgeIndex(index);
    setShowKnowledgeModal(true);
  };

  const handleRemoveKnowledge = (index: number) => {
    setKnowledgeSources(knowledgeSources.filter((_, i) => i !== index));
    toast.success('Knowledge source removed');
  };

  const handleSaveKnowledge = (row: AgentKnowledgeRow) => {
    if (editingKnowledgeIndex !== null) {
      setKnowledgeSources(knowledgeSources.map((ks, i) => (i === editingKnowledgeIndex ? row : ks)));
    } else {
      setKnowledgeSources([...knowledgeSources, row]);
    }
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
    webhook_slug?: string;
    webhook_key?: string;
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
        app_name: values.app_name,
        event_name: values.event_name,
        webhook_slug: values.webhook_slug,
        webhook_key: values.webhook_key,
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
          onSave={handleFormSubmit}
          onRunTest={handleRunTest}
          onDuplicate={handleDuplicate}
          onViewLogs={handleViewLogs}
          onDelete={handleDelete}
          agentId={!isNew && id ? id : undefined}
          allowChat={allowChat}
          lastRun={agentStats.last_run}
          totalRun={agentStats.total_run}
        />

        <Form {...form}>
          <form onSubmit={handleFormSubmit} className="space-y-6">
            <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">
              <TabsList className="flex h-auto w-full justify-start overflow-x-auto overflow-y-hidden p-1">
                {Object.entries(tabConfig).map(([tabKey, config]) => (
                  <TabsTrigger
                    key={tabKey}
                    value={tabKey}
                    disabled={config.disabled}
                    className="flex-1 shrink-0"
                  >
                    {config.label}
                  </TabsTrigger>
                ))}
              </TabsList>

              <TabsContent value="general" className="space-y-4">
                <GeneralTab
                  form={form}
                  providers={providers}
                  models={models}
                  watchProvider={watchProvider}
                  optimizingPrompt={optimizingPrompt}
                  onOptimizePrompt={handleOptimizePrompt}
                  promptOptions={promptOptions}
                  loadingPrompts={loadingPrompts}
                  showAddNewPrompt
                />
              </TabsContent>

              <TabsContent value="behavior" className="space-y-4">
                <BehaviorTab form={form} />
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
                  onEditTool={handleEditTool}
                  mcpServers={mcpServers}
                  onAddMCP={() => setShowMCPServersModal(true)}
                  onRemoveMCP={handleRemoveMCPServer}
                  onToggleMCP={handleToggleMCPServer}
                  onSyncMCP={handleSyncMCPServer}
                  mcpLoading={mcpLoading}
                />
              </TabsContent>

              <TabsContent value="knowledge" className="space-y-4">
                <KnowledgeTab
                  knowledgeSources={knowledgeSources}
                  onAdd={handleAddKnowledge}
                  onEdit={handleEditKnowledge}
                  onRemove={handleRemoveKnowledge}
                />
              </TabsContent>

              <TabsContent value="permissions" className="space-y-4">
                <PermissionsTab form={form} users={users} roles={roles} />
              </TabsContent>

              <TabsContent value="advanced" className="space-y-4">
                <AdvancedTab form={form} allModels={allModels} />
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

      {/* Select MCP Servers Modal */}
      <SelectMCPServersModal
        open={showMCPServersModal}
        onOpenChange={setShowMCPServersModal}
        selectedServers={mcpServers.map((s) => ({
          name: s.mcp_server,
          server_name: s.server_name || '',
          description: s.description,
          enabled: ((s.mcp_enabled === true || s.mcp_enabled === 1) ? 1 : 0) as 0 | 1,
          server_url: s.server_url || '',
          transport_type: 'http' as const,
        })) as MCPServerDoc[]}
        onAddServers={handleAddMCPServers}
      />

      {/* Agent Knowledge Modal */}
      <AgentKnowledgeModal
        open={showKnowledgeModal}
        onOpenChange={setShowKnowledgeModal}
        onSave={handleSaveKnowledge}
        initialData={editingKnowledgeIndex !== null ? knowledgeSources[editingKnowledgeIndex] : null}
      />

      {/* Tool Form Modal (for editing) */}
      <ToolFormModal
        open={showToolFormModal}
        onOpenChange={(open) => {
          setShowToolFormModal(open);
          if (!open) {
            setEditingToolId(null);
            setToolFormData(null);
          }
        }}
        mode="edit"
        initialData={toolFormData}
        onSubmit={handleToolFormSubmit}
        loading={loadingToolData}
        toolName={editingToolId || undefined}
        currentAgentName={isNew ? undefined : id}
      />
    </div>
  );
}
