import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { useSidebar } from "../ui/sidebar";
import ChatAvatar from "./ChatAvatar";
import { getInitials } from "@/utils/getInitials";
import { getConversation } from "@/services/chatApi";
import { getAgent } from "@/services/agentApi";
import type { AgentDoc } from "@/types/agent.types";

interface ChatWindowProps {
    chatId?: string | null;
}

export default function ChatWindow({ chatId: chatIdProp }: ChatWindowProps){
    const {setOpen} = useSidebar();
    
    // Close sidebar on initial mount only
    useEffect(() => {
        setOpen(false);
    }, []);
    
    return (
        <div className="w-full">
           <ChatWindowHeader chatId={chatIdProp} />
        </div>
    )
}

function ChatWindowHeader({ chatId: chatIdProp }: { chatId?: string | null }){
    const { chatId: routeChatId } = useParams<{ chatId?: string }>();
    const [searchParams] = useSearchParams();
    const chatId = chatIdProp ?? (routeChatId && routeChatId !== 'new' ? routeChatId : null);
    
    const [agent, setAgent] = useState<AgentDoc | null>(null);

    useEffect(() => {
        let cancelled = false;

        async function fetchAgentData() {
            try {
                let agentName: string | null = null;

                // Get agent name from conversation or query params
                if (chatId) {
                    // Existing conversation - get agent from conversation
                    try {
                        const conversation = await getConversation(chatId);
                        if (conversation?.agent) {
                            agentName = conversation.agent;
                        }
                    } catch (error) {
                        console.error('Error fetching conversation:', error);
                        if (!cancelled) {
                            toast.error("Failed to load conversation", {
                                description: "Could not fetch conversation details. Please try again.",
                                duration: 5000,
                            });
                        }
                        return;
                    }
                } else {
                    // New chat - get agent from query params
                    agentName = searchParams.get('agent');
                }

                // Fetch agent details if we have an agent name
                if (agentName) {
                    try {
                        const agentData = await getAgent(agentName);
                        if (!cancelled) {
                            setAgent(agentData);
                        }
                    } catch (error) {
                        console.error('Error fetching agent:', error);
                        if (!cancelled) {
                            toast.error("Failed to load agent", {
                                description: "Could not fetch agent details. Please try again.",
                                duration: 5000,
                            });
                            setAgent(null);
                        }
                    }
                } else {
                    if (!cancelled) {
                        setAgent(null);
                    }
                }
            } catch (error) {
                console.error('Error fetching agent data:', error);
                if (!cancelled) {
                    toast.error("Failed to load agent data", {
                        description: "An unexpected error occurred. Please try again.",
                        duration: 5000,
                    });
                    setAgent(null);
                }
            }
        }

        fetchAgentData();

        return () => {
            cancelled = true;
        };
    }, [chatId, searchParams]);

    if (!agent) {
        return (
            <header className="h-16 px-6 border-b border-zinc-200 flex items-center justify-between bg-white/80 backdrop-blur-md sticky top-0 z-10">
                <div className="flex gap-x-4 items-center">
                    <ChatAvatar variant="chat_ai">?</ChatAvatar>
                    <div className="flex flex-col">
                        <span className="font-semibold text-sm text-zinc-900">No agent selected</span>
                        <span className="text-xs text-zinc-500">Select an agent to start chatting</span>
                    </div>
                </div>
            </header>
        );
    }

    return (
        <header className="h-16 px-6 border-b border-zinc-200 flex items-center justify-between bg-white/80 backdrop-blur-md sticky top-0 z-10">
            <div className="flex gap-x-4 items-center">
                <ChatAvatar variant="chat_ai">
                    {getInitials(agent.agent_name)}
                </ChatAvatar>
                <div className="flex flex-col">
                    <div className="flex gap-x-2 items-center">
                        <span className="font-semibold text-sm text-zinc-900">{agent.agent_name}</span>
                        {agent.model && (
                            <span className="px-1.5 py-0.5 rounded bg-indigo-500/10 border border-indigo-500/20 text-[10px] font-medium text-indigo-400">
                                {agent.model}
                            </span>
                        )}
                    </div>
                    {agent.description && (
                        <span className="text-xs text-zinc-500 max-w-[200px] truncate">
                            {agent.description}
                        </span>
                    )}
                </div>
            </div>
        </header>
    )
}