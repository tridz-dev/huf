import { useSyncExternalStore } from 'react';

export type AgentModality = 'Text' | 'Voice' | 'Both';
export type ComposerMode = 'text' | 'voice' | 'both';

export interface AgentModalityFields {
  agent_modality?: AgentModality | null;
  voice_enabled?: number | boolean | null;
}

/**
 * Voice calls off always means text only, even when `agent_modality` still
 * holds its 'Both' default (the editor's Voice calls switch only flips
 * `voice_enabled`). Unknown agents keep the full composer.
 */
export function resolveComposerMode(fields: AgentModalityFields | undefined): ComposerMode {
  if (!fields) return 'both';
  if (!fields.voice_enabled || fields.agent_modality === 'Text') return 'text';
  return fields.agent_modality === 'Voice' ? 'voice' : 'both';
}

// Keyed by agent so switching agents never shows the previous agent's mode.
const modes = new Map<string, ComposerMode>();
const listeners = new Set<() => void>();

export function publishComposerMode(agentName: string, fields: AgentModalityFields): void {
  const next = resolveComposerMode(fields);
  if (modes.get(agentName) === next) return;
  modes.set(agentName, next);
  listeners.forEach((l) => l());
}

export function resetComposerModes(): void {
  modes.clear();
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useComposerMode(agentName: string): ComposerMode {
  return useSyncExternalStore(
    subscribe,
    () => modes.get(agentName) ?? 'both',
    () => 'both'
  );
}
