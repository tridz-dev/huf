// Memory System Components
// Main exports for the HUF Memory System UI

export { MemoryExplorer } from './MemoryExplorer';
export { MemoryPanel } from './MemoryPanel';
export { MemoryInspector, MemoryInspectorCompact } from './MemoryInspector';

// Hooks
export {
  useMemoryRecords,
  useMemoryRecord,
  useConversationMemory,
  useMemoryPolicies,
  useMemoryProfiles,
  useMemoryStats,
  useMemoryRetrieval,
  useMemorySearch,
} from './hooks/useMemory';

// Types (re-export from types package)
export type {
  MemoryRecord,
  MemoryRecordRow,
  MemoryPolicy,
  MemoryProfile,
  MemoryFilters,
  MemoryStats,
  MemoryCaptureResult,
  MemoryRetrievalResult,
  MemoryFormValues,
  MemorySourceType,
  MemoryProducerMode,
  MemoryType,
  MemoryScopeType,
  MemoryVisibility,
  MemoryStatus,
  MemoryIndexBackend,
  MemoryCaptureStage,
  MemoryCaptureFrequency,
  MemoryRetrievalMode,
} from '@/types/memory.types';
