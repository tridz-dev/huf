import type { ToolUIPart } from 'ai';

export type MessageType = {
  key: string;
  from: 'user' | 'assistant';
  versions: {
    id: string;
    content: string;
  }[];
  kind?: string;
  generatedImage?: string;
  generatedAudio?: string;
  generatedVideo?: string;
  voiceMessage?: string;
  runStatus?: 'Queued' | 'Started' | 'Success' | 'Failed';
  /** Links a user bubble to the Agent Run that created it (for merge/hydration). */
  agentRunId?: string;
  error?: string;
  sttModel?: string;
  status?: string;
  attachment?: {
    name: string;
    label: string;
    previewUrl?: string;
  };
  tools?: {
    tool_call_id: string;
    name: string;
    description: string;
    status: ToolUIPart['state'];
    parameters: Record<string, unknown>;
    result: string | undefined;
    error: string | undefined;
    /** Client-side wall-clock timestamp (ms) captured when the tool first entered a running state. Frontend-only approximation, not exact server timing. */
    startedAt?: number;
    /** Elapsed ms between startedAt and the tool reaching a terminal (output-available/output-error) state. */
    durationMs?: number;
  }[];
  injected_memories?: string[];
  /** Provider thinking/reasoning text, shown collapsed above the answer. */
  reasoning?: string;
  reasoningStreaming?: boolean;
};
