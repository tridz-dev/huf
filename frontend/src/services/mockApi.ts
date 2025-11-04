import { Agent, AgentConversation, AgentRun, AIProvider, AIModel, AgentToolFunctionRef } from '../types/agent.types';

const delay = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

const providers: AIProvider[] = [
  { name: "openai", provider_name: "OpenAI" },
  { name: "anthropic", provider_name: "Anthropic" },
  { name: "google", provider_name: "Google" },
];

const models: AIModel[] = [
  { name: "gpt-4", model_name: "GPT-4", provider: "openai" },
  { name: "gpt-3.5-turbo", model_name: "GPT-3.5 Turbo", provider: "openai" },
  { name: "claude-3-opus", model_name: "Claude 3 Opus", provider: "anthropic" },
  { name: "claude-3-sonnet", model_name: "Claude 3 Sonnet", provider: "anthropic" },
  { name: "gemini-pro", model_name: "Gemini Pro", provider: "google" },
];

const toolFunctions: AgentToolFunctionRef[] = [
  {
    name: "get-customer-info",
    tool_name: "Get Customer Info",
    description: "Retrieve customer details from the database",
    types: "Get Document",
    reference_doctype: "Customer",
  },
  {
    name: "create-ticket",
    tool_name: "Create Support Ticket",
    description: "Create a new support ticket",
    types: "Create Document",
    reference_doctype: "Support Ticket",
  },
  {
    name: "send-email",
    tool_name: "Send Email",
    description: "Send an email notification",
    types: "Custom Function",
    function_path: "agentflo.utils.send_email",
  },
];

const mockAgents: Agent[] = [
  {
    name: "1",
    agent_name: "Customer Support Agent",
    provider: "openai",
    model: "gpt-4",
    instructions: "You are a helpful customer support agent. Provide clear, concise answers to customer inquiries.\n\nGoals:\n- Resolve customer issues quickly\n- Maintain a friendly, professional tone\n- Escalate complex issues when needed\n\nConstraints:\n- Always verify customer identity before sharing sensitive information\n- Never make promises about features or timelines without confirmation",
    temperature: 1,
    top_p: 1,
    async: false,
    disabled: false,
    allow_chat: true,
    persist_conversation: true,
    triggers: [
      {
        id: "trigger-1",
        trigger_type: "Webhook",
        active: true,
        webhook_url: "https://api.hufai.com/agent/1/webhook/support-bot",
        webhook_slug: "support-bot",
        created_at: "2025-10-15T08:00:00Z",
      },
      {
        id: "trigger-2",
        trigger_type: "Doc Event",
        active: true,
        reference_doctype: "Support Ticket",
        doc_event: "after_insert",
        condition: "doc.priority == 'High'",
        last_execution: "2025-10-29T14:30:00Z",
        created_at: "2025-10-20T10:00:00Z",
      },
      {
        id: "trigger-3",
        trigger_type: "Doc Event",
        active: true,
        reference_doctype: "Customer",
        doc_event: "on_submit",
        condition: "doc.status == 'Active'",
        last_execution: "2025-10-29T12:15:00Z",
        created_at: "2025-10-22T10:00:00Z",
      },
      {
        id: "trigger-4",
        trigger_type: "Schedule",
        active: true,
        schedule_interval: "Hourly",
        interval_count: 2,
        last_execution: "2025-10-29T16:00:00Z",
        next_execution: "2025-10-29T18:00:00Z",
        created_at: "2025-10-25T10:00:00Z",
      },
      {
        id: "trigger-5",
        trigger_type: "App Event",
        active: true,
        app_name: "Zendesk",
        event_name: "ticket.created",
        last_execution: "2025-10-29T15:45:00Z",
        created_at: "2025-10-26T10:00:00Z",
      },
      {
        id: "trigger-6",
        trigger_type: "Webhook",
        active: false,
        webhook_url: "https://api.hufai.com/agent/1/webhook/escalation",
        webhook_slug: "escalation",
        created_at: "2025-10-27T10:00:00Z",
      },
      {
        id: "trigger-7",
        trigger_type: "Manual",
        active: true,
        created_at: "2025-10-28T10:00:00Z",
      },
    ],
    tags: ["support"],
    category: "Support",
    visibility: "Global",
    environment: "Prod",
    status: "Active",
    tools: [toolFunctions[0], toolFunctions[1]],
    stats: {
      conversations: 234,
      lastRunAt: "2025-10-28T10:30:00Z",
      successRate: 94.5,
      avgCost: 0.023,
      avgLatencyMs: 1240,
      token24h: { input: 45000, output: 32000, total: 77000 },
    },
    created_at: "2025-09-15T08:00:00Z",
    updated_at: "2025-10-28T10:30:00Z",
  },
  {
    name: "2",
    agent_name: "Data Analyst Agent",
    provider: "anthropic",
    model: "claude-3-opus",
    instructions: "Analyze data and generate actionable insights.",
    temperature: 0.7,
    top_p: 1,
    async: false,
    disabled: false,
    allow_chat: true,
    persist_conversation: true,
    triggers: [
      {
        id: "trigger-8",
        trigger_type: "Schedule",
        active: true,
        schedule_interval: "Daily",
        interval_count: 1,
        last_execution: "2025-10-29T06:00:00Z",
        next_execution: "2025-10-30T06:00:00Z",
        created_at: "2025-10-01T00:00:00Z",
      },
      {
        id: "trigger-9",
        trigger_type: "Schedule",
        active: true,
        schedule_interval: "Weekly",
        interval_count: 1,
        last_execution: "2025-10-22T06:00:00Z",
        next_execution: "2025-10-29T06:00:00Z",
        created_at: "2025-10-05T00:00:00Z",
      },
      {
        id: "trigger-10",
        trigger_type: "App Event",
        active: false,
        app_name: "Slack",
        event_name: "message.posted",
        created_at: "2025-10-10T00:00:00Z",
      },
    ],
    tags: ["analytics"],
    category: "Operations",
    visibility: "Team",
    environment: "Prod",
    status: "Active",
    tools: [],
    stats: {
      conversations: 156,
      lastRunAt: "2025-10-28T09:15:00Z",
      successRate: 97.2,
      avgCost: 0.018,
      avgLatencyMs: 980,
      token24h: { input: 28000, output: 19000, total: 47000 },
    },
    created_at: "2025-09-20T10:00:00Z",
    updated_at: "2025-10-28T09:15:00Z",
  },
];

const mockConversations: AgentConversation[] = [];
const mockRuns: AgentRun[] = [];

export const mockApi = {
  providers: {
    list: async (): Promise<AIProvider[]> => {
      await delay(100);
      return providers;
    },
  },
  models: {
    list: async (providerId?: string): Promise<AIModel[]> => {
      await delay(100);
      if (providerId) return models.filter(m => m.provider === providerId);
      return models;
    },
  },
  toolFunctions: {
    list: async (): Promise<AgentToolFunctionRef[]> => {
      await delay(100);
      return toolFunctions;
    },
  },
  agents: {
    list: async (): Promise<Agent[]> => {
      await delay(150);
      return mockAgents;
    },
    get: async (id: string): Promise<Agent | undefined> => {
      await delay(100);
      return mockAgents.find(a => a.name === id);
    },
  },
  conversations: {
    list: async (_agentId?: string): Promise<AgentConversation[]> => {
      await delay(100);
      return mockConversations;
    },
  },
  runs: {
    list: async (_agentId?: string): Promise<AgentRun[]> => {
      await delay(100);
      return mockRuns;
    },
  },
};
