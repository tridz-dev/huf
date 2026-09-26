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
    status: 'Queued' | 'Started' | 'Success' | 'Failed' | 'Waiting Authentication';
    response?: string;
    error?: string;
    agent_message_id?: string;
    sequence?: number;
    /** Subscription Runtime this run is parked on. Only present when
     * `status` is `'Waiting Authentication'` — see
     * `SubscriptionPassthroughExecutor._park_for_auth`, which publishes this
     * alongside the custom `subscription_auth_required` event so any
     * consumer that only watches standard run-status events still learns
     * which runtime to resume/poll/cancel via `SubscriptionAuthCard`. */
    runtime_name?: string;
};

export type ConversationTitleUpdatedEvent = {
    type: 'conversation_title_updated';
    conversation_id: string;
    title: string;
};

export type FrontendToolCallEvent = {
    type: 'frontend_tool_call_initiated';
    conversation_id: string;
    agent_run_id: string;
    message_id: string;
    call_id?: string;
    tool_call_ref?: string;
    function_name: string;
    tool_params?: Record<string, unknown>;
};

export type OpenArtifactPaneEvent = {
    type: 'open_artifact_pane';
    conversation_id: string;
    artifact_id: string;
};

/**
 * Emitted by `SubscriptionPassthroughExecutor._park_for_auth`
 * (huf/ai/subscription/executor.py) when a run is parked waiting on a
 * subscription-runtime login. Field names match that publish call exactly —
 * do not rename without updating the backend. A companion standard
 * `agent_run_status` event with `status: "Waiting Authentication"` is also
 * published alongside this one (same payload minus the challenge fields),
 * so this event only needs to add the challenge/runtime details on top of
 * whatever `onAgentRunStatus` already did.
 */
export type SubscriptionAuthRequiredEvent = {
    type: 'subscription_auth_required';
    agent_run_id: string;
    conversation_id: string;
    runtime_name: string;
    auth_challenge?: string;
    verification_url?: string;
    user_code?: string;
    mode?: string;
};

type ChatSocketProps = {
    conversationId: string | null;
    onToolUpdate?: (event: ToolCallEvent) => void;
    onNewMessage?: (event: NewAgentMessageEvent) => void;
    onAgentRunStatus?: (event: AgentRunStatusEvent) => void;
    onConversationTitleUpdated?: (event: ConversationTitleUpdatedEvent) => void;
    onFrontendToolCall?: (event: FrontendToolCallEvent) => void;
    onOpenArtifactPane?: (event: OpenArtifactPaneEvent) => void;
    onSubscriptionAuthRequired?: (event: SubscriptionAuthRequiredEvent) => void;
}

export function useChatSocket({ conversationId, onToolUpdate, onNewMessage, onAgentRunStatus, onConversationTitleUpdated, onFrontendToolCall, onOpenArtifactPane, onSubscriptionAuthRequired }: ChatSocketProps) {
    const socket = useSocket();

    useEffect(() => {
        if (!socket || !conversationId) {
            return;
        }

        // Listen for conversation-specific events on the shared socket
        const handler = (data: NewAgentMessageEvent | ToolCallEvent | AgentRunStatusEvent | ConversationTitleUpdatedEvent | FrontendToolCallEvent | OpenArtifactPaneEvent | SubscriptionAuthRequiredEvent) => {
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
            } else if (data.type === 'frontend_tool_call_initiated') {
                onFrontendToolCall?.(data as FrontendToolCallEvent);
            } else if (data.type === 'open_artifact_pane') {
                onOpenArtifactPane?.(data as OpenArtifactPaneEvent);
            } else if (data.type === 'subscription_auth_required') {
                onSubscriptionAuthRequired?.(data as SubscriptionAuthRequiredEvent);
            }
        };

        socket.on(`conversation:${conversationId}`, handler);

        return () => {
            // Only detach this conversation's listener - the shared socket
            // itself is owned by SocketProvider and stays connected.
            socket.off(`conversation:${conversationId}`, handler);
        };
    }, [socket, conversationId, onToolUpdate, onNewMessage, onAgentRunStatus, onConversationTitleUpdated, onFrontendToolCall, onOpenArtifactPane, onSubscriptionAuthRequired]);
}