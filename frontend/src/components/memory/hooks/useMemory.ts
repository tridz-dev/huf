import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import type {
  MemoryRecord,
  MemoryRecordRow,
  MemoryPolicy,
  MemoryProfile,
  MemoryFilters,
  MemoryStats,
  MemoryCaptureResult,
  MemoryRetrievalResult,
  MemoryScopeType,
  MemoryType,
  MemoryStatus,
} from '@/types/memory.types';
import {
  getMemoryRecords,
  getMemoryRecord,
  createMemoryRecord,
  updateMemoryRecord,
  deleteMemoryRecord,
  searchMemoryRecords,
  getConversationMemoryRecords,
  captureConversationMemory,
  getMemoryPolicies,
  getMemoryPolicy,
  createMemoryPolicy,
  updateMemoryPolicy,
  deleteMemoryPolicy,
  getMemoryProfiles,
  getMemoryProfile,
  getMemoryStats,
  retrieveMemories,
} from '@/services/memoryApi';

// ============================================================================
// useMemoryRecords - Hook for fetching and managing memory records list
// ============================================================================

interface UseMemoryRecordsOptions {
  filters?: MemoryFilters;
  autoFetch?: boolean;
}

export function useMemoryRecords(options: UseMemoryRecordsOptions = {}) {
  const { filters = {}, autoFetch = true } = options;
  const [records, setRecords] = useState<MemoryRecordRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const hasFetchedRef = useRef(false);

  const fetchRecords = useCallback(async (overrideFilters?: MemoryFilters) => {
    setLoading(true);
    setError(null);
    try {
      const result = await getMemoryRecords(overrideFilters || filters);
      setRecords(result);
      return result;
    } catch (err) {
      setError(err as Error);
      throw err;
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    if (autoFetch && !hasFetchedRef.current) {
      hasFetchedRef.current = true;
      fetchRecords();
    }
  }, [autoFetch, fetchRecords]);

  const refetch = useCallback(() => {
    return fetchRecords();
  }, [fetchRecords]);

  return {
    records,
    loading,
    error,
    refetch,
    setRecords,
  };
}

// ============================================================================
// useMemoryRecord - Hook for single memory record operations
// ============================================================================

interface UseMemoryRecordOptions {
  name?: string;
  autoFetch?: boolean;
}

export function useMemoryRecord(options: UseMemoryRecordOptions = {}) {
  const { name, autoFetch = true } = options;
  const [record, setRecord] = useState<MemoryRecord | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const hasFetchedRef = useRef(false);

  const fetchRecord = useCallback(async (recordName: string) => {
    setLoading(true);
    setError(null);
    try {
      const result = await getMemoryRecord(recordName);
      setRecord(result);
      return result;
    } catch (err) {
      setError(err as Error);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (name && autoFetch && !hasFetchedRef.current) {
      hasFetchedRef.current = true;
      fetchRecord(name);
    }
  }, [name, autoFetch, fetchRecord]);

  const create = useCallback(async (data: Partial<MemoryRecord>) => {
    setLoading(true);
    setError(null);
    try {
      const result = await createMemoryRecord(data);
      setRecord(result);
      return result;
    } catch (err) {
      setError(err as Error);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const update = useCallback(async (recordName: string, data: Partial<MemoryRecord>) => {
    setLoading(true);
    setError(null);
    try {
      const result = await updateMemoryRecord(recordName, data);
      setRecord(result);
      return result;
    } catch (err) {
      setError(err as Error);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const remove = useCallback(async (recordName: string) => {
    setLoading(true);
    setError(null);
    try {
      await deleteMemoryRecord(recordName);
      setRecord(null);
    } catch (err) {
      setError(err as Error);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  return {
    record,
    loading,
    error,
    fetchRecord,
    create,
    update,
    remove,
    setRecord,
  };
}

// ============================================================================
// useConversationMemory - Hook for memory related to a specific conversation
// ============================================================================

interface UseConversationMemoryOptions {
  conversationId?: string;
  autoFetch?: boolean;
}

export function useConversationMemory(options: UseConversationMemoryOptions = {}) {
  const { conversationId, autoFetch = true } = options;
  const [records, setRecords] = useState<MemoryRecordRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [captureResult, setCaptureResult] = useState<MemoryCaptureResult | null>(null);
  const hasFetchedRef = useRef(false);

  const fetchRecords = useCallback(async (convId: string) => {
    setLoading(true);
    setError(null);
    try {
      const result = await getConversationMemoryRecords(convId);
      setRecords(result);
      return result;
    } catch (err) {
      setError(err as Error);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (conversationId && autoFetch && !hasFetchedRef.current) {
      hasFetchedRef.current = true;
      fetchRecords(conversationId);
    }
  }, [conversationId, autoFetch, fetchRecords]);

  const capture = useCallback(async (convId?: string) => {
    const targetId = convId || conversationId;
    if (!targetId) throw new Error('Conversation ID is required');
    
    setLoading(true);
    setError(null);
    try {
      const result = await captureConversationMemory(targetId);
      setCaptureResult(result);
      // Refresh records after capture
      await fetchRecords(targetId);
      return result;
    } catch (err) {
      setError(err as Error);
      throw err;
    } finally {
      setLoading(false);
    }
  }, [conversationId, fetchRecords]);

  return {
    records,
    loading,
    error,
    captureResult,
    fetchRecords,
    capture,
    setRecords,
  };
}

// ============================================================================
// useMemoryPolicies - Hook for managing memory policies
// ============================================================================

interface UseMemoryPoliciesOptions {
  agent?: string;
  autoFetch?: boolean;
}

export function useMemoryPolicies(options: UseMemoryPoliciesOptions = {}) {
  const { agent, autoFetch = true } = options;
  const [policies, setPolicies] = useState<MemoryPolicy[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const hasFetchedRef = useRef(false);

  const fetchPolicies = useCallback(async (agentFilter?: string) => {
    setLoading(true);
    setError(null);
    try {
      const result = await getMemoryPolicies(agentFilter || agent);
      setPolicies(result);
      return result;
    } catch (err) {
      setError(err as Error);
      throw err;
    } finally {
      setLoading(false);
    }
  }, [agent]);

  useEffect(() => {
    if (autoFetch && !hasFetchedRef.current) {
      hasFetchedRef.current = true;
      fetchPolicies();
    }
  }, [autoFetch, fetchPolicies]);

  const create = useCallback(async (data: Partial<MemoryPolicy>) => {
    setLoading(true);
    setError(null);
    try {
      const result = await createMemoryPolicy(data);
      setPolicies((prev) => [result, ...prev]);
      return result;
    } catch (err) {
      setError(err as Error);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const update = useCallback(async (name: string, data: Partial<MemoryPolicy>) => {
    setLoading(true);
    setError(null);
    try {
      const result = await updateMemoryPolicy(name, data);
      setPolicies((prev) =>
        prev.map((p) => (p.name === name ? result : p))
      );
      return result;
    } catch (err) {
      setError(err as Error);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const remove = useCallback(async (name: string) => {
    setLoading(true);
    setError(null);
    try {
      await deleteMemoryPolicy(name);
      setPolicies((prev) => prev.filter((p) => p.name !== name));
    } catch (err) {
      setError(err as Error);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  return {
    policies,
    loading,
    error,
    fetchPolicies,
    create,
    update,
    remove,
    setPolicies,
  };
}

// ============================================================================
// useMemoryProfiles - Hook for memory profiles
// ============================================================================

interface UseMemoryProfilesOptions {
  category?: string;
  autoFetch?: boolean;
}

export function useMemoryProfiles(options: UseMemoryProfilesOptions = {}) {
  const { category, autoFetch = true } = options;
  const [profiles, setProfiles] = useState<MemoryProfile[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const hasFetchedRef = useRef(false);

  const fetchProfiles = useCallback(async (categoryFilter?: string) => {
    setLoading(true);
    setError(null);
    try {
      const result = await getMemoryProfiles(categoryFilter || category);
      setProfiles(result);
      return result;
    } catch (err) {
      setError(err as Error);
      throw err;
    } finally {
      setLoading(false);
    }
  }, [category]);

  useEffect(() => {
    if (autoFetch && !hasFetchedRef.current) {
      hasFetchedRef.current = true;
      fetchProfiles();
    }
  }, [autoFetch, fetchProfiles]);

  const getProfile = useCallback(async (name: string) => {
    setLoading(true);
    setError(null);
    try {
      const result = await getMemoryProfile(name);
      return result;
    } catch (err) {
      setError(err as Error);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  return {
    profiles,
    loading,
    error,
    fetchProfiles,
    getProfile,
    setProfiles,
  };
}

// ============================================================================
// useMemoryStats - Hook for memory statistics
// ============================================================================

interface UseMemoryStatsOptions {
  autoFetch?: boolean;
  refreshInterval?: number; // in milliseconds
}

export function useMemoryStats(options: UseMemoryStatsOptions = {}) {
  const { autoFetch = true, refreshInterval } = options;
  const [stats, setStats] = useState<MemoryStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const hasFetchedRef = useRef(false);

  const fetchStats = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await getMemoryStats();
      setStats(result);
      return result;
    } catch (err) {
      setError(err as Error);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (autoFetch && !hasFetchedRef.current) {
      hasFetchedRef.current = true;
      fetchStats();
    }
  }, [autoFetch, fetchStats]);

  useEffect(() => {
    if (refreshInterval) {
      const interval = setInterval(fetchStats, refreshInterval);
      return () => clearInterval(interval);
    }
  }, [refreshInterval, fetchStats]);

  return {
    stats,
    loading,
    error,
    refetch: fetchStats,
    setStats,
  };
}

// ============================================================================
// useMemoryRetrieval - Hook for retrieving memories for injection
// ============================================================================

interface UseMemoryRetrievalOptions {
  agent: string;
  conversation?: string;
  user?: string;
  scopeType?: MemoryScopeType;
  autoFetch?: boolean;
}

export function useMemoryRetrieval(options: UseMemoryRetrievalOptions) {
  const { agent, conversation, user, scopeType, autoFetch = false } = options;
  const [result, setResult] = useState<MemoryRetrievalResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const retrieve = useCallback(async (params?: {
    query?: string;
    limit?: number;
  }) => {
    setLoading(true);
    setError(null);
    try {
      const result = await retrieveMemories({
        agent,
        conversation,
        user,
        scope_type: scopeType,
        ...params,
      });
      setResult(result);
      return result;
    } catch (err) {
      setError(err as Error);
      throw err;
    } finally {
      setLoading(false);
    }
  }, [agent, conversation, user, scopeType]);

  useEffect(() => {
    if (autoFetch) {
      retrieve();
    }
  }, [autoFetch, retrieve]);

  return {
    result,
    loading,
    error,
    retrieve,
    setResult,
  };
}

// ============================================================================
// useMemorySearch - Hook for searching memory records
// ============================================================================

export function useMemorySearch() {
  const [results, setResults] = useState<MemoryRecordRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const search = useCallback(async (query: string) => {
    if (!query.trim()) {
      setResults([]);
      return [];
    }
    
    setLoading(true);
    setError(null);
    try {
      const result = await searchMemoryRecords(query);
      setResults(result);
      return result;
    } catch (err) {
      setError(err as Error);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const clear = useCallback(() => {
    setResults([]);
    setError(null);
  }, []);

  return {
    results,
    loading,
    error,
    search,
    clear,
    setResults,
  };
}
