import { db } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import { handleFrappeError } from '@/lib/frappe-error';
import type { PaginationParams, PaginatedResponse } from '@/types/pagination';

export type ArtifactType = 'JSON' | 'File' | 'Text';
export type ArtifactVisibility =
  | 'user_visible'
  | 'model_visible'
  | 'ui_only'
  | 'audit_only'
  | 'developer_only';

export interface AgentContextArtifactDoc {
  name: string;
  conversation?: string;
  agent_run?: string;
  artifact_type?: ArtifactType;
  summary?: string;
  payload_json?: string;
  payload_file?: string;
  reference_doctype?: string;
  reference_name?: string;
  visibility?: ArtifactVisibility;
  context_policy?: string;
  token_estimate?: number;
  expires_on?: string;
  creation?: string;
  modified?: string;
}

export interface ArtifactListParams extends PaginationParams {
  conversation?: string;
  agent_run?: string;
  artifact_type?: string;
  visibility?: string;
}

const LIST_FIELDS = [
  'name',
  'conversation',
  'agent_run',
  'artifact_type',
  'summary',
  'visibility',
  'context_policy',
  'token_estimate',
  'creation',
];

export async function getArtifacts(
  params: ArtifactListParams = {}
): Promise<PaginatedResponse<AgentContextArtifactDoc>> {
  const { limit = 20, start = 0, conversation, agent_run, artifact_type, visibility } = params;

  const filters: Array<[string, string, unknown]> = [];
  if (conversation) filters.push(['conversation', '=', conversation]);
  if (agent_run) filters.push(['agent_run', '=', agent_run]);
  if (artifact_type && artifact_type !== 'all') filters.push(['artifact_type', '=', artifact_type]);
  if (visibility && visibility !== 'all') filters.push(['visibility', '=', visibility]);

  try {
    const artifacts = await db.getDocList(doctype['Agent Context Artifact'], {
      fields: LIST_FIELDS,
      filters: (filters.length ? filters : undefined) as any,
      orderBy: { field: 'creation', order: 'desc' },
      limit: limit + 1,
      limit_start: start,
    });

    const hasMore = artifacts.length > limit;
    return {
      data: (hasMore ? artifacts.slice(0, limit) : artifacts) as AgentContextArtifactDoc[],
      hasMore,
    };
  } catch (error) {
    handleFrappeError(error, 'Error fetching context artifacts');
    return { data: [], hasMore: false };
  }
}

export async function getArtifact(name: string): Promise<AgentContextArtifactDoc | undefined> {
  try {
    return await db.getDoc(doctype['Agent Context Artifact'], name);
  } catch (error) {
    handleFrappeError(error, `Error fetching context artifact ${name}`);
  }
}
