import { db, call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';
import type {
  MemoryRecord,
  MemoryRecordRow,
  MemoryPolicy,
  MemoryProfile,
  MemoryFilters,
  MemoryStats,
  MemoryCaptureResult,
  MemoryRetrievalResult,
} from '@/types/memory.types';

// Doctypes
const MEMORY_RECORD_DOCTYPE = 'Agent Memory Record';
const MEMORY_POLICY_DOCTYPE = 'Memory Policy';
const MEMORY_PROFILE_DOCTYPE = 'Memory Profile';

/**
 * Fields for memory record listing
 */
const MEMORY_RECORD_LIST_FIELDS = [
  'name',
  'title',
  'agent',
  'agent_name',
  'memory_type',
  'scope_type',
  'status',
  'confidence',
  'importance_score',
  'tags',
  'creation',
  'modified',
];

/**
 * Fields for memory policy listing
 */
const MEMORY_POLICY_LIST_FIELDS = [
  'name',
  'policy_name',
  'enabled',
  'agent',
  'memory_profile',
  'capture_owner',
  'capture_stage',
  'retrieval_mode_default',
];

/**
 * Fields for memory profile listing
 */
const MEMORY_PROFILE_LIST_FIELDS = [
  'name',
  'profile_name',
  'description',
  'category',
  'is_system_profile',
];

/**
 * Fetch memory records with optional filters
 */
export async function getMemoryRecords(filters?: MemoryFilters): Promise<MemoryRecordRow[]> {
  try {
    const filterConditions: Record<string, string | string[]> = {};
    
    if (filters?.scope_type) filterConditions.scope_type = filters.scope_type;
    if (filters?.agent) filterConditions.agent = filters.agent;
    if (filters?.memory_type) filterConditions.memory_type = filters.memory_type;
    if (filters?.profile_name) filterConditions.profile_name = filters.profile_name;
    if (filters?.status) filterConditions.status = filters.status;
    if (filters?.tags?.length) filterConditions.tags = ['like', `%${filters.tags.join(',')}%`];
    if (filters?.fts_indexed !== undefined) filterConditions.fts_indexed = filters.fts_indexed ? '1' : '0';
    if (filters?.vector_indexed !== undefined) filterConditions.vector_indexed = filters.vector_indexed ? '1' : '0';
    
    const result = await db.getDocList<MemoryRecordRow>(MEMORY_RECORD_DOCTYPE, {
      fields: MEMORY_RECORD_LIST_FIELDS,
      filters: Object.keys(filterConditions).length > 0 ? filterConditions : undefined,
      orderBy: { field: 'modified', order: 'desc' },
      limit: 100,
    });
    
    return result;
  } catch (error) {
    handleFrappeError(error, 'Error fetching memory records');
    throw error;
  }
}

/**
 * Fetch a single memory record by name
 */
export async function getMemoryRecord(name: string): Promise<MemoryRecord> {
  try {
    const result = await db.getDoc<MemoryRecord>(MEMORY_RECORD_DOCTYPE, name);
    return result;
  } catch (error) {
    handleFrappeError(error, `Error fetching memory record ${name}`);
    throw error;
  }
}

/**
 * Create a new memory record
 */
export async function createMemoryRecord(data: Partial<MemoryRecord>): Promise<MemoryRecord> {
  try {
    const result = await db.createDoc<MemoryRecord>(MEMORY_RECORD_DOCTYPE, data);
    return result;
  } catch (error) {
    handleFrappeError(error, 'Error creating memory record');
    throw error;
  }
}

/**
 * Update an existing memory record
 */
export async function updateMemoryRecord(
  name: string,
  data: Partial<MemoryRecord>
): Promise<MemoryRecord> {
  try {
    const result = await db.updateDoc<MemoryRecord>(MEMORY_RECORD_DOCTYPE, name, data);
    return result;
  } catch (error) {
    handleFrappeError(error, `Error updating memory record ${name}`);
    throw error;
  }
}

/**
 * Delete a memory record
 */
export async function deleteMemoryRecord(name: string): Promise<void> {
  try {
    await db.deleteDoc(MEMORY_RECORD_DOCTYPE, name);
  } catch (error) {
    handleFrappeError(error, `Error deleting memory record ${name}`);
    throw error;
  }
}

/**
 * Search memory records by text query
 */
export async function searchMemoryRecords(query: string): Promise<MemoryRecordRow[]> {
  try {
    const result = await call.post('huf.huf.doctype.agent_memory_record.agent_memory_record.search', {
      query,
    });
    return result.message as MemoryRecordRow[];
  } catch (error) {
    handleFrappeError(error, 'Error searching memory records');
    throw error;
  }
}

/**
 * Fetch memory records for a specific conversation
 */
export async function getConversationMemoryRecords(conversationId: string): Promise<MemoryRecordRow[]> {
  try {
    const result = await db.getDocList<MemoryRecordRow>(MEMORY_RECORD_DOCTYPE, {
      fields: MEMORY_RECORD_LIST_FIELDS,
      filters: { conversation: conversationId },
      orderBy: { field: 'creation', order: 'desc' },
    });
    return result;
  } catch (error) {
    handleFrappeError(error, 'Error fetching conversation memory records');
    throw error;
  }
}

/**
 * Trigger manual memory capture for a conversation
 */
export async function captureConversationMemory(conversationId: string): Promise<MemoryCaptureResult> {
  try {
    const result = await call.post('huf.huf.doctype.agent_memory_record.agent_memory_record.capture', {
      conversation: conversationId,
    });
    return result.message as MemoryCaptureResult;
  } catch (error) {
    handleFrappeError(error, 'Error capturing conversation memory');
    throw error;
  }
}

/**
 * Fetch memory policies
 */
export async function getMemoryPolicies(agent?: string): Promise<MemoryPolicy[]> {
  try {
    const filters: Record<string, string> = {};
    if (agent) filters.agent = agent;
    
    const result = await db.getDocList<MemoryPolicy>(MEMORY_POLICY_DOCTYPE, {
      fields: MEMORY_POLICY_LIST_FIELDS,
      filters: Object.keys(filters).length > 0 ? filters : undefined,
      orderBy: { field: 'modified', order: 'desc' },
    });
    return result;
  } catch (error) {
    handleFrappeError(error, 'Error fetching memory policies');
    throw error;
  }
}

/**
 * Fetch a single memory policy
 */
export async function getMemoryPolicy(name: string): Promise<MemoryPolicy> {
  try {
    const result = await db.getDoc<MemoryPolicy>(MEMORY_POLICY_DOCTYPE, name);
    return result;
  } catch (error) {
    handleFrappeError(error, `Error fetching memory policy ${name}`);
    throw error;
  }
}

/**
 * Create a memory policy
 */
export async function createMemoryPolicy(data: Partial<MemoryPolicy>): Promise<MemoryPolicy> {
  try {
    const result = await db.createDoc<MemoryPolicy>(MEMORY_POLICY_DOCTYPE, data);
    return result;
  } catch (error) {
    handleFrappeError(error, 'Error creating memory policy');
    throw error;
  }
}

/**
 * Update a memory policy
 */
export async function updateMemoryPolicy(
  name: string,
  data: Partial<MemoryPolicy>
): Promise<MemoryPolicy> {
  try {
    const result = await db.updateDoc<MemoryPolicy>(MEMORY_POLICY_DOCTYPE, name, data);
    return result;
  } catch (error) {
    handleFrappeError(error, `Error updating memory policy ${name}`);
    throw error;
  }
}

/**
 * Delete a memory policy
 */
export async function deleteMemoryPolicy(name: string): Promise<void> {
  try {
    await db.deleteDoc(MEMORY_POLICY_DOCTYPE, name);
  } catch (error) {
    handleFrappeError(error, `Error deleting memory policy ${name}`);
    throw error;
  }
}

/**
 * Fetch memory profiles
 */
export async function getMemoryProfiles(category?: string): Promise<MemoryProfile[]> {
  try {
    const filters: Record<string, string> = {};
    if (category) filters.category = category;
    
    const result = await db.getDocList<MemoryProfile>(MEMORY_PROFILE_DOCTYPE, {
      fields: MEMORY_PROFILE_LIST_FIELDS,
      filters: Object.keys(filters).length > 0 ? filters : undefined,
      orderBy: { field: 'is_system_profile', order: 'desc' },
    });
    return result;
  } catch (error) {
    handleFrappeError(error, 'Error fetching memory profiles');
    throw error;
  }
}

/**
 * Fetch a single memory profile
 */
export async function getMemoryProfile(name: string): Promise<MemoryProfile> {
  try {
    const result = await db.getDoc<MemoryProfile>(MEMORY_PROFILE_DOCTYPE, name);
    return result;
  } catch (error) {
    handleFrappeError(error, `Error fetching memory profile ${name}`);
    throw error;
  }
}

/**
 * Fetch memory statistics
 */
export async function getMemoryStats(): Promise<MemoryStats> {
  try {
    const result = await call.get('huf.huf.doctype.agent_memory_record.agent_memory_record.get_stats');
    return result.message as MemoryStats;
  } catch (error) {
    handleFrappeError(error, 'Error fetching memory statistics');
    throw error;
  }
}

/**
 * Retrieve memories for injection into a prompt
 */
export async function retrieveMemories(params: {
  agent: string;
  conversation?: string;
  user?: string;
  query?: string;
  scope_type?: string;
  limit?: number;
}): Promise<MemoryRetrievalResult> {
  try {
    const result = await call.post('huf.huf.doctype.agent_memory_record.agent_memory_record.retrieve', params);
    return result.message as MemoryRetrievalResult;
  } catch (error) {
    handleFrappeError(error, 'Error retrieving memories');
    throw error;
  }
}
