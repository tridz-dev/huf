import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';

/**
 * HUF Project document shape, as returned by huf.ai.project_api.
 */
export interface HufProject {
  name: string;
  project_name: string;
  description?: string;
  instructions?: string;
  default_agent?: string;
  status: 'Open' | 'Archived' | string;
  last_activity?: string;
  owner?: string;
  creation?: string;
  modified?: string;
}

export interface ListProjectsParams {
  status?: string;
}

export interface CreateProjectParams {
  project_name: string;
  description?: string;
  instructions?: string;
  default_agent?: string;
}

export interface UpdateProjectParams {
  project: string;
  project_name?: string;
  description?: string;
  instructions?: string;
  default_agent?: string;
  status?: string;
}

/** Pin metadata returned by pin_conversation / stored in Conversation Pin. */
export interface ConversationPin {
  name: string;
  user: string;
  conversation: string;
  pinned_at: string;
}

export interface UnpinConversationResponse {
  success: boolean;
}

/** Agent Conversation summary fields returned by get_pinned_conversations. */
export interface PinnedConversation {
  name: string;
  title: string;
  agent: string;
  project?: string;
  model?: string;
  last_activity?: string;
  channel?: string;
  pinned_at?: string;
}

export interface SetConversationProjectResponse {
  conversation: string;
  project: string | null;
}

/**
 * List HUF Projects visible to the current user.
 */
export async function listProjects(params: ListProjectsParams = {}): Promise<HufProject[]> {
  try {
    const result = await call.get('huf.ai.project_api.list_projects', {
      status: params.status ?? undefined,
    });
    return (result?.message ?? result) as HufProject[];
  } catch (error) {
    handleFrappeError(error, 'Error fetching projects');
    return [];
  }
}

/**
 * Get a single HUF Project.
 */
export async function getProject(project: string): Promise<HufProject | undefined> {
  try {
    const result = await call.get('huf.ai.project_api.get_project', { project });
    return (result?.message ?? result) as HufProject;
  } catch (error) {
    handleFrappeError(error, 'Error fetching project');
  }
}

/**
 * Create a new HUF Project.
 */
export async function createProject(params: CreateProjectParams): Promise<HufProject> {
  try {
    const result = await call.post('huf.ai.project_api.create_project', {
      project_name: params.project_name,
      description: params.description ?? undefined,
      instructions: params.instructions ?? undefined,
      default_agent: params.default_agent ?? undefined,
    });
    return (result?.message ?? result) as HufProject;
  } catch (error) {
    handleFrappeError(error, 'Error creating project');
    throw error;
  }
}

/**
 * Update an existing HUF Project.
 */
export async function updateProject(params: UpdateProjectParams): Promise<HufProject> {
  try {
    const result = await call.post('huf.ai.project_api.update_project', {
      project: params.project,
      project_name: params.project_name ?? undefined,
      description: params.description ?? undefined,
      instructions: params.instructions ?? undefined,
      default_agent: params.default_agent ?? undefined,
      status: params.status ?? undefined,
    });
    return (result?.message ?? result) as HufProject;
  } catch (error) {
    handleFrappeError(error, 'Error updating project');
    throw error;
  }
}

/**
 * Archive a HUF Project (status transition, not a destructive delete).
 */
export async function archiveProject(project: string): Promise<HufProject> {
  try {
    const result = await call.post('huf.ai.project_api.archive_project', { project });
    return (result?.message ?? result) as HufProject;
  } catch (error) {
    handleFrappeError(error, 'Error archiving project');
    throw error;
  }
}

/**
 * Pin a conversation for the current user. Idempotent.
 */
export async function pinConversation(conversation: string): Promise<ConversationPin> {
  try {
    const result = await call.post('huf.ai.project_api.pin_conversation', { conversation });
    return (result?.message ?? result) as ConversationPin;
  } catch (error) {
    handleFrappeError(error, 'Error pinning conversation');
    throw error;
  }
}

/**
 * Unpin a conversation for the current user. Idempotent.
 */
export async function unpinConversation(conversation: string): Promise<UnpinConversationResponse> {
  try {
    const result = await call.post('huf.ai.project_api.unpin_conversation', { conversation });
    return (result?.message ?? result) as UnpinConversationResponse;
  } catch (error) {
    handleFrappeError(error, 'Error unpinning conversation');
    return { success: false };
  }
}

/**
 * List the current user's pinned conversations, most recently pinned first,
 * optionally scoped to a Project.
 */
export async function getPinnedConversations(project?: string): Promise<PinnedConversation[]> {
  try {
    const result = await call.get('huf.ai.project_api.get_pinned_conversations', {
      project: project ?? undefined,
    });
    return (result?.message ?? result) as PinnedConversation[];
  } catch (error) {
    handleFrappeError(error, 'Error fetching pinned conversations');
    return [];
  }
}

/**
 * Move an existing Agent Conversation in or out of a Project.
 * Pass `project: null` (or omit) to clear the conversation's project.
 */
export async function setConversationProject(
  conversation: string,
  project?: string | null
): Promise<SetConversationProjectResponse> {
  try {
    const result = await call.post('huf.ai.project_api.set_conversation_project', {
      conversation,
      project: project ?? undefined,
    });
    return (result?.message ?? result) as SetConversationProjectResponse;
  } catch (error) {
    handleFrappeError(error, 'Error moving conversation');
    throw error;
  }
}
