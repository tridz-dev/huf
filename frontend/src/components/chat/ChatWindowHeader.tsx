import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Bot, PanelLeftOpen } from "lucide-react";
import { Button } from "../ui/button";
import { Badge } from "../ui/badge";
import ChatAvatar from "./ChatAvatar";
import { getInitials } from "@/utils/getInitials";
import { getConversation } from "@/services/chatApi";
import { getAgent } from "@/services/agentApi";
import type { AgentDoc } from "@/types/agent.types";
import { DEFAULT_AGENT_COLOR } from "@/data/color";
import { ConversationDataPanel } from "@/components/conversation/ConversationDataPanel";

interface ChatWindowHeaderProps {
    chatId?: string | null;
    sidebarOpen?: boolean;
    onToggleSidebar?: () => void;
}

export function ChatWindowHeader({
    chatId: chatIdProp,
    onToggleSidebar,
}: ChatWindowHeaderProps) {
    const { chatId: routeChatId } = useParams<{ chatId?: string }>();
    const [searchParams] = useSearchParams();
    const chatId = chatIdProp ?? (routeChatId && routeChatId !== 'new' ? routeChatId : null);
    
    const [agent, setAgent] = useState<AgentDoc | null>(null);
    const [conversationModel, setConversationModel] = useState<string | null>(null);

    useEffect(() => {
        let cancelled = false;

        if (!chatId) {
            setConversationModel(null);
        }

        async function fetchAgentData() {
            try {
                let agentName: string | null = null;
                let model: string | null = null;

                if (chatId) {
                    try {
                        const conversation = await getConversation(chatId);
                        if (conversation?.agent) {
                            agentName = conversation.agent;
                        }
                        if (conversation?.model) {
                            model = conversation.model;
                        }
                        if (!cancelled) {
                            setConversationModel(model);
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
                    agentName = searchParams.get('agent');
                }

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

    const showOpenSidebarBtn = !!onToggleSidebar;

    if (!agent) {
        return (
            <header className="h-16 pl-4 md:pl-14 pr-6 border-b border-line flex items-center justify-between bg-panel sticky top-0 z-10">
                <div className="flex gap-x-3 items-center">
                    {showOpenSidebarBtn && (
                        <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 text-steel hover:text-ink"
                            onClick={onToggleSidebar}
                        >
                            <PanelLeftOpen className="w-4 h-4" />
                            <span className="sr-only">Open conversations</span>
                        </Button>
                    )}
                    <ChatAvatar variant="chat_ai">?</ChatAvatar>
                    <div className="flex flex-col">
                        <span className="font-semibold text-sm text-ink">No agent selected</span>
                        <span className="text-xs text-steel">Select an agent to start chatting</span>
                    </div>
                </div>
            </header>
        );
    }

    return (
        <header className="h-16 pl-4 md:pl-14 pr-6 border-b border-line flex items-center justify-between bg-panel sticky top-0 z-10">
            <div className="flex gap-x-3 items-center">
                {showOpenSidebarBtn && (
                    <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-steel hover:text-ink"
                        onClick={onToggleSidebar}
                    >
                        <PanelLeftOpen className="w-4 h-4" />
                        <span className="sr-only">Open conversations</span>
                    </Button>
                )}
                <ChatAvatar variant="chat_ai" color={agent.agent_color || DEFAULT_AGENT_COLOR}>
                    {getInitials(agent.agent_name)}
                </ChatAvatar>
                <div className="flex flex-col">
                    <div className="flex gap-x-2 items-center">
                        <span className="font-semibold text-sm text-ink">{agent.agent_name}</span>
                        {(conversationModel || agent.model) && (
                            <Badge variant="outline" className="shrink-0">
                                {conversationModel || agent.model}
                            </Badge>
                        )}
                    </div>
                    {agent.description && (
                        <span className="text-xs text-steel max-w-[200px] truncate">
                            {agent.description}
                        </span>
                    )}
                </div>
            </div>
            <div className="flex items-center gap-2">
                {chatId && agent.enable_conversation_data === 1 && (
                    <ConversationDataPanel
                        conversationId={chatId}
                        canWrite={agent.conversation_data_api_permission === 'Write'}
                    />
                )}
                <Link to={`/agents/${agent.name}`}>
                    <Button asChild variant="outline" className="gap-x-2 text-xs text-muted-foreground" size="sm">
                        <div>
                            <Bot className="w-4 h-4" />
                            <span>Open Agent</span>
                        </div>
                    </Button>
                </Link>
            </div>
        </header>
    );
}
