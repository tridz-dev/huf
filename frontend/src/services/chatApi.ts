import type { Filter } from 'frappe-js-sdk/lib/db/types';
import { db, call } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import { handleFrappeError } from '@/lib/frappe-error';
import { PaginationParams, PaginatedResponse } from '@/types/pagination';
import { fetchDocCount } from './utilsApi';

/**
 * Agent Conversation document from Frappe
 */
export interface AgentConversationDoc {
  name: string;
  title: string;
  agent: string;
  model?: string;
  last_activity?: string;
  modified?: string;
}

/**
 * Chat list item (mapped from Agent Conversation)
 */
export interface ChatListItem {
  id: string;
  title: string;
  agent: string;
  /**
   * Raw timestamp (ISO/datetime string from Frappe).
   * Use `timestampLabel` for display-friendly formatting.
   */
  timestamp?: string;
  /**
   * UI-friendly label (e.g. "2m ago"). Populated by UI hooks.
   */
  timestampLabel?: string;
}

type ConversationFilter = [keyof AgentConversationDoc | string, string, unknown];

export interface AgentMessageDoc {
  name: string;
  conversation: string;
  content: string;
  is_agent_message?: 0 | 1 | string;
  agent_run?: string;
  kind?: string;
  generated_image?: string;
  generated_audio?: string;
  generated_video?: string;
  voice_message?: string;
  stt_model?: string;
  status?: string;
  tool_name?: string;
  tool_status?: string;
  tool_args?: string | Record<string, unknown>;
  creation?: string;
  modified?: string;
}

export interface ChatMessage {
  id: string;
  conversation: string;
  content: string;
  isAgent: boolean;
  agentRun?: string;
  kind?: string;
  generatedImage?: string;
  generatedAudio?: string;
  generatedVideo?: string;
  voiceMessage?: string;
  sttModel?: string;
  status?: string;
  toolName?: string;
  toolStatus?: string;
  toolArgs?: string | Record<string, unknown>;
  injectedMemories?: string[];
  createdAt?: string;
  updatedAt?: string;
}

/** Open Agent Run for a conversation (Queued or Started). */
export interface PendingConversationRun {
  name: string;
  status: 'Queued' | 'Started' | string;
  prompt?: string | null;
  sequence?: number | null;
  conversation?: string | null;
}

/**
 * Map Agent Conversation document to chat list item
 */
function mapChatListItem(doc: AgentConversationDoc): ChatListItem {
  return {
    id: doc.name,
    title: doc.title || 'Untitled Chat',
    agent: doc.agent || '',
    timestamp: doc.last_activity || doc.modified || undefined,
  };
}

function mapAgentMessage(doc: AgentMessageDoc): ChatMessage {
  const isAgent = doc.is_agent_message === 1;

  return {
    id: doc.name,
    conversation: doc.conversation,
    content: doc.content || '',
    isAgent,
    agentRun: doc.agent_run || undefined,
    kind: doc.kind,
    generatedImage: doc.generated_image,
    generatedAudio: doc.generated_audio,
    generatedVideo: doc.generated_video,
    voiceMessage: doc.voice_message,
    sttModel: doc.stt_model,
    status: doc.status,
    toolName: doc.tool_name,
    toolStatus: doc.tool_status,
    toolArgs: doc.tool_args,
    createdAt: doc.creation,
    updatedAt: doc.modified,
  };
}

/**
 * Parameters for fetching paginated conversations
 */
export interface ConversationListParams extends PaginationParams {
  filters?: ConversationFilter[];
}

export interface ConversationMessageListParams extends PaginationParams {
  conversation?: string;
}

/**
 * Fetch paginated agent conversations sorted by last updated time.
 */
export async function getConversations(
  params: ConversationListParams = {}
): Promise<PaginatedResponse<ChatListItem>> {
  const { limit = 20, start = 0, search, filters } = params;

  try {
    const effectiveFilters: Filter<Record<string, unknown>>[] | undefined =
      (filters as Filter<Record<string, unknown>>[] | undefined) ??
      (search ? [['title', 'like', `%${search}%`]] : undefined);

    const conversations = await db.getDocList(doctype['Agent Conversation'], {
      fields: ['name', 'title', 'agent', 'last_activity', 'modified'],
      orderBy: { field: 'modified', order: 'desc' },
      limit,
      limit_start: start,
      filters: effectiveFilters,
    });

    const mapped = (conversations as AgentConversationDoc[]).map(mapChatListItem);
    return {
      data: mapped,
      hasMore: mapped.length === limit,
    };
  } catch (error) {
    handleFrappeError(error, 'Error fetching conversations');
  }
}

/**
 * Agent with conversation count (for "By Agent" tab)
 */
export interface AgentWithCount {
  name: string;
  agent_name: string;
  conversationCount: number;
  last_updated?: string;
  agent_color?: string | null;
  provider?: string;
  model?: string;
  allow_chat?: number;
}

/**
 * Fetch agents sorted by last updated, with conversation counts.
 * Used for "By Agent" tab to show agents without loading all conversations.
 */
export async function getAgentsWithConversationCounts(): Promise<AgentWithCount[]> {
  try {
    // Fetch all agents sorted by last updated (modified field)
    const agents = await db.getDocList(doctype.Agent, {
      fields: ['name', 'agent_name', 'modified', 'agent_color', 'provider', 'model', 'allow_chat'],
      filters: [['allow_chat', '=', 1]],
      orderBy: { field: 'modified', order: 'asc' },
      limit: 1000, // Reasonable limit for agents
    });

    // Fetch conversation count for each agent
    const agentsWithCounts: AgentWithCount[] = await Promise.all(
      (agents as Array<{
        name: string;
        agent_name: string;
        modified?: string;
        agent_color?: string | null;
        provider?: string;
        model?: string;
        allow_chat?: number;
      }>).map(async (agent) => {
        let count = 0;
        try {
          count = (await fetchDocCount(doctype['Agent Conversation'], [
            ['agent', '=', agent.name],
            ['channel', '=', 'Chat'],
          ])) || 0;
        } catch (error) {
          // One agent's conversation count being denied/unavailable must not
          // drop every other agent from the "By Agent" listing.
          console.error(`Error fetching conversation count for agent ${agent.name}:`, error);
        }
        return {
          name: agent.name,
          agent_name: agent.agent_name || agent.name,
          conversationCount: count,
          last_updated: agent.modified,
          agent_color: agent.agent_color || null,
          provider: agent.provider,
          model: agent.model,
          allow_chat: agent.allow_chat,
        };
      })
    );

    // Filter out agents with 0 conversations and sort by last updated
    return agentsWithCounts
      .filter((agent) => agent.conversationCount > 0)
      .sort((a, b) => {
        const aTime = a.last_updated ? new Date(a.last_updated).getTime() : 0;
        const bTime = b.last_updated ? new Date(b.last_updated).getTime() : 0;
        return bTime - aTime; // Descending (newest first)
      });
  } catch (error) {
    handleFrappeError(error, 'Error fetching agents with conversation counts');
    return [];
  }
}

/**
 * Fetch conversations for a specific agent.
 * Used for lazy loading when user opens an agent accordion.
 */
export async function getConversationsByAgent(
  agentName: string,
  params: { limit?: number; start?: number } = {}
): Promise<PaginatedResponse<ChatListItem>> {
  const { limit = 100, start = 0 } = params;

  try {
    const conversations = await db.getDocList(doctype['Agent Conversation'], {
      fields: ['name', 'title', 'agent', 'last_activity', 'modified'],
      filters: [
        ['agent', '=', agentName],
        ['channel', '=', 'Chat'],
      ],
      orderBy: { field: 'modified', order: 'desc' },
      limit,
      limit_start: start,
    });

    const mapped = (conversations as AgentConversationDoc[]).map(mapChatListItem);
    return {
      data: mapped,
      hasMore: mapped.length === limit,
    };
  } catch (error) {
    handleFrappeError(error, `Error fetching conversations for agent ${agentName}`);
    return {
      data: [],
      hasMore: false,
    };
  }
}

/**
 * Fetch all conversations for date grouping (Recents tab).
 * Fetches a large batch to properly group by date.
 */
export async function getAllConversationsForRecents(
  limit: number = 500
): Promise<ChatListItem[]> {
  try {
    const conversations = await db.getDocList(doctype['Agent Conversation'], {
      fields: ['name', 'title', 'agent', 'last_activity', 'modified'],
      filters: [['channel', '=', 'Chat']],
      orderBy: { field: 'modified', order: 'desc' },
      limit,
    });

    return (conversations as AgentConversationDoc[]).map(mapChatListItem);
  } catch (error) {
    handleFrappeError(error, 'Error fetching all conversations for recents');
    return [];
  }
}

/**
 * Fetch a single conversation
 */
export async function getConversation(conversationId: string): Promise<AgentConversationDoc | undefined> {
  try {
    const conversation = await db.getDoc(doctype['Agent Conversation'], conversationId);
    return conversation as AgentConversationDoc;
  } catch (error) {
    handleFrappeError(error, 'Error fetching conversation');
  }
}

/**
 * Load messages for a specific conversation, ordered from newest to oldest
 */
export async function getConversationMessages(
  params: ConversationMessageListParams
): Promise<PaginatedResponse<ChatMessage>> {
  const { conversation, limit = 30, start = 0 } = params;

  if (!conversation) {
    return {
      data: [],
      hasMore: false,
      total: 0,
    };
  }

  try {
    const messages = await db.getDocList(doctype['Agent Message'], {
      fields: ['name', 'conversation', 'content', 'is_agent_message', 'agent_run', 'kind', 'generated_image', 'generated_audio', 'generated_video', 'voice_message', 'stt_model', 'status', 'tool_name', 'tool_status', 'tool_args', 'creation', 'modified'],
      filters: [['conversation', '=', conversation]],
      orderBy: { field: 'creation', order: 'desc' },
      limit,
      limit_start: start,
    });

    const mapped = (messages as AgentMessageDoc[]).map(mapAgentMessage);
    const ordered = mapped.slice().reverse();

    return {
      data: ordered,
      hasMore: mapped.length === limit,
    };
  } catch (error) {
    handleFrappeError(error, 'Error fetching conversation messages');
  }
}

/**
 * Transcribe audio only (no agent run). Returns transcript for streaming flow.
 */
export interface TranscribeAudioParams {
  filename: string;
  b64data: string;
  agent: string;
  conversation?: string;
  modelOverride?: string;
}

export interface TranscribeAudioResponse {
  success: boolean;
  conversation_id?: string;
  transcript?: string;
  message_id?: string;
  error?: string;
  file_url?: string;
}

export async function transcribeAudio(
  params: TranscribeAudioParams
): Promise<TranscribeAudioResponse> {
  try {
    const result = await call.post('huf.ai.agent_chat.upload_audio_and_transcribe_web', {
      filename: params.filename,
      b64data: params.b64data,
      agent: params.agent,
      conversation: params.conversation ?? undefined,
      transcribe_only: true,
      model_override: params.modelOverride ?? undefined,
    });
    return (result?.message ?? result) as TranscribeAudioResponse;
  } catch (error) {
    handleFrappeError(error, 'Error transcribing audio');
  }
}

export interface UploadFileParams {
  filename: string;
  b64data: string;
  agent: string;
  conversation?: string;
  modelOverride?: string;
}

export interface UploadFileResponse {
  success: boolean;
  conversation_id?: string;
  message_id?: string;
  text?: string;
  file_name?: string;
  error?: string;
}

export async function uploadFileAndProcess(
  params: UploadFileParams
): Promise<UploadFileResponse> {
  try {
    const result = await call.post('huf.ai.agent_chat.upload_file_and_process_web', {
      filename: params.filename,
      b64data: params.b64data,
      agent: params.agent,
      conversation: params.conversation ?? undefined,
      model_override: params.modelOverride ?? undefined,
    });
    return (result?.message ?? result) as UploadFileResponse;
  } catch (error) {
    handleFrappeError(error, 'Error uploading file');
    return { success: false, error: 'Error uploading file' };
  }
}

export interface UploadFileAttachmentParams {
  filename: string;
  b64data: string;
  agent: string;
  modelOverride?: string;
}

export interface UploadFileAttachmentResponse {
  success: boolean;
  file_id?: string;
  file_url?: string;
  filename?: string;
  error?: string;
}

export async function uploadFileAttachment(
  params: UploadFileAttachmentParams
): Promise<UploadFileAttachmentResponse> {
  try {
    const result = await call.post('huf.ai.agent_chat.upload_file_attachment_web', {
      filename: params.filename,
      b64data: params.b64data,
      agent: params.agent,
      model_override: params.modelOverride ?? undefined,
    });
    return (result?.message ?? result) as UploadFileAttachmentResponse;
  } catch (error) {
    handleFrappeError(error, 'Error uploading file');
    return { success: false, error: 'Error uploading file' };
  }
}

export interface PrepareMessageWithFileParams {
  file_id: string;
  filename: string;
  agent: string;
  conversation?: string;
  message?: string;
  modelOverride?: string;
}

export interface PrepareMessageWithFileFile {
  file_id: string;
  file_url: string;
  filename: string;
  is_image: number;
}

export interface PrepareMessageWithFileResponse {
  success: boolean;
  conversation_id?: string;
  message_id?: string;
  agent_prompt?: string;
  files?: PrepareMessageWithFileFile[];
  error?: string;
  is_audio?: boolean;
  transcript?: string;
  voice_message?: string;
  stt_model?: string;
}

export async function prepareMessageWithFile(
  params: PrepareMessageWithFileParams
): Promise<PrepareMessageWithFileResponse> {
  try {
    const result = await call.post('huf.ai.agent_chat.prepare_message_with_file_web', {
      file_id: params.file_id,
      filename: params.filename,
      agent: params.agent,
      conversation: params.conversation ?? undefined,
      message: params.message ?? '',
      model_override: params.modelOverride ?? undefined,
    });
    return (result?.message ?? result) as PrepareMessageWithFileResponse;
  } catch (error) {
    handleFrappeError(error, 'Error preparing file attachment');
    return { success: false, error: 'Error preparing file attachment' };
  }
}

/**
 * A backend-initiated client-side ("frontend") tool call as it appears in
 * the `client_side_tool_calls` array on the send-message / new-conversation
 * HTTP response. Mirrors the same call the backend may also announce via the
 * `frontend_tool_call_initiated` socket event -- see
 * doc/domain/queue-first-execution-model.md design rule 4 (pending-state UI
 * must reconcile via polling/response data, not rely on the socket alone).
 */
export interface ClientToolCallPayload {
  id: string;
  type: 'function';
  function: {
    name: string;
    /** JSON-encoded arguments; must be parsed by the caller. */
    arguments: string;
  };
  /** Agent Tool Call docname -- present alongside `id` for some call sites. */
  tool_call_ref?: string;
}

/**
 * Start a new conversation
 */
export interface NewConversationParams {
  agent: string;
  message: string;
  /** The user message was already persisted (e.g. file/audio prepare step). */
  skip_user_message?: boolean;
  files?: PrepareMessageWithFileFile[];
  modelOverride?: string;
}

export interface NewConversationResponse {
  message: {
    success: boolean;
    conversation_id: string;
    queued?: boolean;
    status?: string;
    agent_run_id?: string;
    agent_message_id?: string;
    sequence?: number;
    run?: {
      success: boolean;
      response: string;
      structured: unknown;
      provider: string;
      agent_run_id: string;
      conversation_id: string;
      session_id: string;
      client_side_tool_calls?: ClientToolCallPayload[];
    };
  };
}

/**
 * Send message to an existing conversation
 */
export interface SendMessageParams {
  conversation: string;
  message: string;
  /** The user message was already persisted (e.g. file/audio prepare step). */
  skip_user_message?: boolean;
  files?: PrepareMessageWithFileFile[];
  modelOverride?: string;
}

export interface SendMessageResponse {
  message: {
    success: boolean;
    response?: string;
    structured?: unknown;
    provider?: string;
    agent_run_id: string;
    conversation_id: string;
    session_id: string;
    queued?: boolean;
    status?: string;
    agent_message_id?: string;
    sequence?: number;
    client_side_tool_calls?: ClientToolCallPayload[];
  };
}

/**
 * Start a new conversation
 */
export async function newConversation(
  params: NewConversationParams
): Promise<NewConversationResponse> {
  try {
    const result = await call.post('huf.ai.agent_chat.new_conversation', {
      agent: params.agent,
      message: params.message,
      skip_user_message: params.skip_user_message ? 1 : 0,
      files: params.files,
      model_override: params.modelOverride ?? undefined,
    });
    return result as NewConversationResponse;
  } catch (error) {
    handleFrappeError(error, 'Error creating new conversation');
  }
}

/**
 * Send a message to an existing conversation
 */
export async function sendMessageToConversation(
  params: SendMessageParams
): Promise<SendMessageResponse> {
  try {
    const result = await call.post('huf.ai.agent_chat.send_message_to_conversation', {
      conversation: params.conversation,
      message: params.message,
      skip_user_message: params.skip_user_message ? 1 : 0,
      files: params.files,
      model_override: params.modelOverride ?? undefined,
    });
    return result as SendMessageResponse;
  } catch (error) {
    handleFrappeError(error, 'Error sending message to conversation');
  }
}

export interface SetConversationModelOverrideParams {
  conversation: string;
  modelOverride?: string | null;
}

export interface SetConversationModelOverrideResponse {
  success: boolean;
  conversation_id?: string;
  model?: string;
}

export async function setConversationModelOverride(
  params: SetConversationModelOverrideParams
): Promise<SetConversationModelOverrideResponse> {
  try {
    const result = await call.post('huf.ai.agent_chat.set_conversation_model_override', {
      conversation: params.conversation,
      model_override: params.modelOverride ?? undefined,
    });
    return (result?.message ?? result) as SetConversationModelOverrideResponse;
  } catch (error) {
    handleFrappeError(error, 'Error setting conversation model');
    return { success: false };
  }
}

/**
 * Submit agent run feedback
 */
export interface AgentRunFeedbackParams {
  agent: string;
  feedback: 'Thumbs Up' | 'Thumbs Down';
  comments?: string;
  conversation?: string;
  agent_message?: string;
}

export async function createAgentRunFeedback(params: AgentRunFeedbackParams): Promise<void> {
  try {
    await db.createDoc(doctype['Agent Run Feedback'], {
      agent: params.agent,
      feedback: params.feedback,
      comments: params.comments,
      conversation: params.conversation,
      agent_message: params.agent_message,
    });
  } catch (error) {
    handleFrappeError(error, 'Error submitting feedback');
  }
}

export async function updateConversationTitle(conversationId:string,title:string){
  try{
    await db.updateDoc(doctype['Agent Conversation'],conversationId,{
      title
    })
  }catch(e){
    handleFrappeError(e,"Error update conversation title")
  }
}

export interface SubmitClientToolResultParams {
  callId: string;
  result?: unknown;
  error?: string;
}

export interface SubmitClientToolResultResponse {
  success: boolean;
}

/**
 * Submit the result of a browser-executed ("frontend") tool call back to the backend.
 */
export async function submitClientToolResult(
  params: SubmitClientToolResultParams
): Promise<SubmitClientToolResultResponse> {
  try {
    const result = await call.post('huf.ai.client_side_tool.submit_client_tool_result', {
      call_id: params.callId,
      result: params.result,
      error: params.error,
    });
    return (result?.message ?? result) as SubmitClientToolResultResponse;
  } catch (error) {
    handleFrappeError(error, 'Error submitting client tool result');
  }
}

export type ForkMode = 'full_history' | 'summary' | 'last_output';

export interface ForkConversationParams {
  conversationId: string;
  mode: ForkMode;
  title?: string;
}

export interface ForkConversationResponse {
  success: boolean;
  conversation_id: string;
  title: string;
}

export async function forkConversation(
  params: ForkConversationParams
): Promise<ForkConversationResponse> {
  try {
    const result = await call.post('huf.ai.agent_chat.fork_conversation', {
      conversation_id: params.conversationId,
      mode: params.mode,
      title: params.title,
    });
    return (result?.message ?? result) as ForkConversationResponse;
  } catch (error) {
    handleFrappeError(error, 'Error forking conversation');
  }
}

export interface AgentRunFeedbackDoc {
  name: string;
  agent: string;
  feedback: 'Thumbs Up' | 'Thumbs Down';
  comments?: string;
  conversation?: string;
  agent_message?: string;
}

export async function getAgentMessageIdForRun(agentRunId: string): Promise<string | undefined> {
  try {
    const messages = await db.getDocList(doctype['Agent Message'], {
      fields: ['name'],
      filters: [
        ['agent_run', '=', agentRunId],
        ['is_agent_message', '=', 1],
      ],
      orderBy: { field: 'creation', order: 'desc' },
      limit: 1,
    });

    const first = (messages as Array<{ name: string }>)[0];
    return first?.name;
  } catch (error) {
    handleFrappeError(error, 'Error fetching agent message for run');
  }
}

/**
 * Response of huf.ai.agent_integration.get_agent_run_status.
 * Statuses match the Agent Run doctype Select options.
 */
export interface AgentRunStatusResponse {
  success: boolean;
  queued?: boolean;
  status: 'Queued' | 'Started' | 'Success' | 'Failed';
  response?: string | null;
  error?: string | null;
  agent_run_id: string;
  conversation_id?: string;
  agent?: string;
  agent_message_id?: string | null;
}

/**
 * Fetch the status of a queued agent run.
 * Polling fallback for missed `agent_run_status` socket events.
 */
/**
 * Fetch open (Queued/Started) agent runs for a conversation.
 * Used to hydrate pending bubbles after reload or chat switch.
 */
export async function getPendingConversationRuns(
  conversationId: string
): Promise<PendingConversationRun[]> {
  if (!conversationId) {
    return [];
  }

  try {
    const runs = await db.getDocList(doctype['Agent Run'], {
      fields: ['name', 'status', 'prompt', 'sequence', 'conversation'],
      filters: [
        ['conversation', '=', conversationId],
        ['status', 'in', ['Queued', 'Started']],
        ['is_child', '=', 0],
      ],
      orderBy: { field: 'sequence', order: 'asc' },
      limit: 50,
    });

    return (runs as PendingConversationRun[]).slice().sort((a, b) => {
      const seqA = a.sequence ?? 0;
      const seqB = b.sequence ?? 0;
      if (seqA !== seqB) return seqA - seqB;
      return a.name.localeCompare(b.name);
    });
  } catch (error) {
    handleFrappeError(error, 'Error fetching pending conversation runs');
    return [];
  }
}

export async function getAgentRunStatus(agentRunId: string): Promise<AgentRunStatusResponse> {
  try {
    const result = await call.get('huf.ai.agent_integration.get_agent_run_status', {
      agent_run_id: agentRunId,
    });
    return (result?.message ?? result) as AgentRunStatusResponse;
  } catch (error) {
    handleFrappeError(error, 'Error fetching agent run status');
  }
}

export async function getExistingRunFeedback(
  agentMessageId: string
): Promise<AgentRunFeedbackDoc | undefined> {
  try {
    const feedback = await db.getDocList(doctype['Agent Run Feedback'], {
      fields: ['name', 'agent', 'feedback', 'comments', 'conversation', 'agent_message'],
      filters: [['agent_message', '=', agentMessageId]],
      limit: 1,
    });

    return (feedback as AgentRunFeedbackDoc[])[0];
  } catch (error) {
    handleFrappeError(error, 'Error fetching run feedback');
  }
}
