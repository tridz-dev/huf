import { useEffect, useState, useCallback, useRef } from 'react';

import { getConversation } from '@/services/chatApi';
import { getAgent } from '@/services/agentApi';

/** localStorage key for cross-tab sync of the tool-execution-details toggle */
function toolDetailsKey(agent: string): string {
  return `huf:agent:${agent}:show_tool_execution_details`;
}

/** Write the setting to localStorage so other tabs can pick it up via the `storage` event. */
export function writeToolDetailsSetting(agent: string, enabled: boolean): void {
  try {
    localStorage.setItem(toolDetailsKey(agent), enabled ? '1' : '0');
  } catch {
    // Storage full or unavailable – non-critical
  }
}

export function useChatAgentIdentity(chatId: string | null, searchParams: URLSearchParams, defaultAgentName?: string) {
  const [agentName, setAgentName] = useState<string>('');
  const [agentColor, setAgentColor] = useState<string | null>(null);
  const [showToolExecutionDetails, setShowToolExecutionDetails] = useState<boolean>(true);
  const agentNameRef = useRef<string>('');

  // Keep ref in sync so async callbacks see the latest value
  agentNameRef.current = agentName;

  /** Apply the value from the API and cache it in localStorage */
  const applyToolDetails = useCallback((agent: string, value: 0 | 1 | undefined) => {
    const enabled = value === 1;
    setShowToolExecutionDetails(enabled);
    writeToolDetailsSetting(agent, enabled);
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function loadFromConversation(conversationId: string) {
      try {
        const conversation = await getConversation(conversationId);
        if (!conversation?.agent) return;

        if (!cancelled) setAgentName(conversation.agent);

        try {
          const agentData = await getAgent(conversation.agent);
          if (!cancelled) {
            setAgentColor(agentData.agent_color || null);
            applyToolDetails(conversation.agent, agentData.show_tool_execution_details);
          }
        } catch (error) {
          console.error('Failed to load agent color', error);
          if (!cancelled) {
            setAgentColor(null);
            setShowToolExecutionDetails(true);
          }
        }
      } catch (error) {
        console.error('Failed to load conversation agent', error);
      }
    }

    async function loadFromQueryParam() {
      const agentFromQuery = searchParams.get('agent') ?? defaultAgentName ?? '';
      if (!cancelled) setAgentName(agentFromQuery);

      if (!agentFromQuery) {
        if (!cancelled) {
          setAgentColor(null);
          setShowToolExecutionDetails(true);
        }
        return;
      }

      try {
        const agentData = await getAgent(agentFromQuery);
        if (!cancelled) {
          setAgentColor(agentData.agent_color || null);
          applyToolDetails(agentFromQuery, agentData.show_tool_execution_details);
        }
      } catch (error) {
        console.error('Failed to load agent color', error);
        if (!cancelled) {
          setAgentColor(null);
          setShowToolExecutionDetails(true);
        }
      }
    }

    if (chatId) loadFromConversation(chatId);
    else loadFromQueryParam();

    return () => {
      cancelled = true;
    };
  }, [chatId, searchParams, applyToolDetails, defaultAgentName]);

  // ── Cross-tab sync via localStorage `storage` event ──────────────
  // Instant sync when another tab in the SAME React SPA writes to localStorage
  useEffect(() => {
    if (!agentName) return;

    const expectedKey = toolDetailsKey(agentName);

    function handleStorageChange(event: StorageEvent) {
      if (event.key !== expectedKey) return;
      if (event.newValue === '1') setShowToolExecutionDetails(true);
      else if (event.newValue === '0') setShowToolExecutionDetails(false);
    }

    window.addEventListener('storage', handleStorageChange);
    return () => window.removeEventListener('storage', handleStorageChange);
  }, [agentName]);

  // ── Re-fetch from API when tab regains focus ─────────────────────
  // Handles ALL save methods: React SPA, Frappe desk form, API/scripts
  useEffect(() => {
    if (!agentName) return;
    let cancelled = false;

    function handleVisibilityChange() {
      if (document.visibilityState !== 'visible') return;
      const currentAgent = agentNameRef.current;
      if (!currentAgent) return;

      // Re-fetch the authoritative value from the server
      getAgent(currentAgent)
        .then((agentData) => {
          if (cancelled) return;
          applyToolDetails(currentAgent, agentData.show_tool_execution_details);
        })
        .catch(() => {
          // Non-critical – keep existing value
        });
    }

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => {
      cancelled = true;
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [agentName, applyToolDetails]);

  return { agentName, agentColor, showToolExecutionDetails };
}
