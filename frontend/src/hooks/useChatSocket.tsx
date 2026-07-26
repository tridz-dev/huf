import { useEffect } from 'react';
import { useSocket } from '../contexts/SocketContext';

export type ToolCallEvent = {
    type: 'tool_call_started' | 'tool_call_completed' | 'tool_call_failed';
    agent_run_id: string;
    conversation_id: string;
    message_id: string;
    tool_call_id: string;
    tool_name: string;
    tool_status: 'Queued' | 'Started' | 'Completed' | 'Failed';
    tool_args?: Record<string, unknown>;
    tool_result?: Record<string, unknown>;
    error?: string | null;
};

export type NewAgentMessageEvent = {
    type: 'new_agent_message';
    conversation_id: string;
    message_id: string;
    kind?: string;
    content?: string;
    generated_image?: string;
    generated_audio?: string;
    generated_video?: string;
    agent_run_id?: string;
    conversation_index?: number;
    injected_memories?: string[];
};

export type AgentRunStatusEvent = {
    type: 'agent_run_status';
    agent_run_id: string;
    conversation_id: string;
    session_id?: string;
    status: 'Queued' | 'Started' | 'Success' | 'Failed';
    response?: string;
    error?: string;
    agent_message_id?: string;
    sequence?: number;
};

export type ConversationTitleUpdatedEvent = {
    type: 'conversation_title_updated';
    conversation_id: string;
    title: string;
};

type ChatSocketProps = {   
    conversationId: string | null;
    onToolUpdate?: (event: ToolCallEvent) => void;
    onNewMessage?: (event: NewAgentMessageEvent) => void;
    onAgentRunStatus?: (event: AgentRunStatusEvent) => void;
    onConversationTitleUpdated?: (event: ConversationTitleUpdatedEvent) => void;
}

export function useChatSocket({ conversationId, onToolUpdate, onNewMessage, onAgentRunStatus, onConversationTitleUpdated }: ChatSocketProps) {
    const socket = useSocket();

    useEffect(() => {
        if (!socket || !conversationId) {
            return;
        }

        // Listen for conversation-specific events on the shared socket
        const handler = (data: NewAgentMessageEvent | ToolCallEvent | AgentRunStatusEvent | ConversationTitleUpdatedEvent) => {
            console.log("Conversation event received:", data);

            // Route to appropriate handler based on event type
            if (data.type === 'new_agent_message') {
                onNewMessage?.(data as NewAgentMessageEvent);
            } else if (
                data.type === 'tool_call_started' ||
                data.type === 'tool_call_completed' ||
                data.type === 'tool_call_failed'
            ) {
                onToolUpdate?.(data as ToolCallEvent);
            } else if (data.type === 'agent_run_status') {
                onAgentRunStatus?.(data as AgentRunStatusEvent);
            } else if (data.type === 'conversation_title_updated') {
                onConversationTitleUpdated?.(data as ConversationTitleUpdatedEvent);
            }
        };

        socket.on(`conversation:${conversationId}`, handler);

        return () => {
            // Only detach this conversation's listener - the shared socket
            // itself is owned by SocketProvider and stays connected.
            socket.off(`conversation:${conversationId}`, handler);
        };
    }, [socket, conversationId, onToolUpdate, onNewMessage, onAgentRunStatus, onConversationTitleUpdated]);
}