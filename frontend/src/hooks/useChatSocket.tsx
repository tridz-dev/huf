import { createFrappeSocket } from '../utils/socket';
import { useEffect } from 'react';

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
    agent_run_id?: string;
    conversation_index?: number;
};

type ChatSocketProps = {   
    conversationId: string | null;
    onToolUpdate?: (event: ToolCallEvent) => void;
    onNewMessage?: (event: NewAgentMessageEvent) => void;
}

export function useChatSocket({ conversationId, onToolUpdate, onNewMessage }: ChatSocketProps) {
    useEffect(() => {
        if (!conversationId) {
            return;
        }

        const siteName = (window as any).frappe?.boot?.sitename;
        // If port is available in the url, use socketio port from the url, otherwise empty
        const port = window.location.port ?  (window as any).frappe?.boot?.socketio_port : ''
        
        if (!siteName) {
            console.warn("Site name not available yet, socket connection will be skipped");
            return;
        }

        const socket = createFrappeSocket({ siteName, port });
        console.log("Socket created for conversation:", conversationId);

        // Listen for conversation-specific events
        socket.on(`conversation:${conversationId}`, (data: any) => {
            console.log("Conversation event received:", data);
            
            // Route to appropriate handler based on event type
            if (data.type === 'new_agent_message') {
                onNewMessage?.(data as NewAgentMessageEvent);
            } else {
                onToolUpdate?.(data as ToolCallEvent);
            }
        });

        socket.on('connect', () => {
            console.log("✅ Socket connected for conversation:", conversationId);
        });

        socket.on('connect_error', (error) => {
            console.error("❌ Socket connection error:", error);
        });

        socket.on('disconnect', (reason) => {
            console.warn("⚠️ Socket disconnected:", reason);
        });

        return () => {
            console.log("Cleaning up socket for conversation:", conversationId);
            socket.off(`conversation:${conversationId}`);
            socket.disconnect();
        };
    }, [conversationId, onToolUpdate, onNewMessage]);
}