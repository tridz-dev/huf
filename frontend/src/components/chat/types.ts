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
  voiceMessage?: string;
  tools?: {
    tool_call_id: string;
    name: string;
    description: string;
    status: ToolUIPart['state'];
    parameters: Record<string, unknown>;
    result: string | undefined;
    error: string | undefined;
  }[];
};
