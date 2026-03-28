/**
 * HUF Memory System - Component exports
 * 
 * This module provides UI components for the HUF Agent Memory system
 * as specified in PRD Section 20: UI/UX Changes
 */

// Main components
export { MemoryPanel } from './MemoryPanel';
export { MemoryExplorer } from './MemoryExplorer';
export { ConversationMemory } from './ConversationMemory';

// Conversation memory sub-components
export {
  MemoryCaptureButton,
  ConversationMemoryPanel,
  MemorySidebar,
  ConversationMemoryIndicator,
  MemoryRecordMini,
} from './ConversationMemory';

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

// Types (re-exported from types module)
export type {
  MemoryFormValues,
} from '@/types/memory.types';
