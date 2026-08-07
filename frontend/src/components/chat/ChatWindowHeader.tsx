import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Check, ChevronDown, PanelLeftOpen, SquareAsterisk } from "lucide-react";
import { Button } from "../ui/button";
import { Badge } from "../ui/badge";
import { Popover, PopoverContent, PopoverTrigger } from "../ui/popover";
import ChatAvatar from "./ChatAvatar";
import { getInitials } from "@/utils/getInitials";
import { getConversation } from "@/services/chatApi";
import { getAgent, getChatAgents, type ChatAgentItem } from "@/services/agentApi";
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
                        <AgentSwitcher currentAgentName={null} triggerLabel="No agent selected" />
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
                        <AgentSwitcher currentAgentName={agent.name} triggerLabel={agent.agent_name} />
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
                            <SquareAsterisk className="w-4 h-4" />
                            <span>Open Agent</span>
                        </div>
                    </Button>
                </Link>
            </div>
        </header>
    );
}

interface AgentSwitcherProps {
    /** Name (doctype id) of the agent currently active in this chat window,
     * or null when no conversation/agent has been resolved yet. */
    currentAgentName: string | null;
    triggerLabel: string;
}

/**
 * Clickable agent name in the chat header. Opens a popover listing the
 * agents available for chat (same `getChatAgents` source as the sidebar's
 * "new chat" picker and the chat-only header) so the user can switch
 * without leaving the conversation view.
 *
 * Picking an agent starts a new chat with that agent rather than mutating
 * the open conversation — conversations are pinned to the agent they were
 * created with (see `useChatAgentIdentity`, which only reads `?agent=` for
 * chats that do not yet have a chatId), so switching mid-conversation has
 * no existing "continue with a different agent" semantics to preserve.
 */
function AgentSwitcher({ currentAgentName, triggerLabel }: AgentSwitcherProps) {
    const navigate = useNavigate();
    const [open, setOpen] = useState(false);
    const [agents, setAgents] = useState<ChatAgentItem[]>([]);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (!open) return;

        let cancelled = false;
        setLoading(true);

        getChatAgents()
            .then((data) => {
                if (!cancelled) setAgents(data);
            })
            .finally(() => {
                if (!cancelled) setLoading(false);
            });

        return () => {
            cancelled = true;
        };
    }, [open]);

    const handleSelect = (agentName: string) => {
        setOpen(false);
        navigate(`/chat?agent=${encodeURIComponent(agentName)}`);
    };

    return (
        <Popover open={open} onOpenChange={setOpen}>
            <PopoverTrigger asChild>
                <button
                    type="button"
                    className="flex items-center gap-1 rounded-md -mx-1 px-1 text-sm font-semibold text-ink hover:bg-paper-deep"
                >
                    <span className="truncate max-w-[200px]">{triggerLabel}</span>
                    <ChevronDown className="w-3.5 h-3.5 shrink-0 text-steel-soft" />
                </button>
            </PopoverTrigger>
            <PopoverContent align="start" className="w-72 p-1">
                <div className="px-2 py-1.5 text-xs font-normal text-steel">Assistants</div>
                {loading ? (
                    <div className="px-2 py-3 text-center text-sm text-steel">Loading agents...</div>
                ) : agents.length === 0 ? (
                    <div className="px-2 py-3 text-center text-sm text-steel">No chat agents available.</div>
                ) : (
                    <div className="max-h-80 overflow-y-auto">
                        {agents.map((agentItem) => (
                            <button
                                key={agentItem.name}
                                type="button"
                                onClick={() => handleSelect(agentItem.name)}
                                className="flex w-full items-center gap-2 rounded-sm px-2 py-2 text-left hover:bg-paper-deep"
                            >
                                <ChatAvatar
                                    variant="listing_ai"
                                    color={agentItem.agent_color || DEFAULT_AGENT_COLOR}
                                >
                                    {getInitials(agentItem.agent_name || agentItem.name)}
                                </ChatAvatar>
                                <span className="min-w-0 flex-1">
                                    <span className="block truncate text-sm text-ink">
                                        {agentItem.agent_name || agentItem.name}
                                    </span>
                                    <span className="block truncate text-xs text-steel">
                                        {agentItem.description || agentItem.model || "Chat agent"}
                                    </span>
                                </span>
                                {agentItem.name === currentAgentName && (
                                    <Check className="size-4 shrink-0 text-primary" />
                                )}
                            </button>
                        ))}
                    </div>
                )}
            </PopoverContent>
        </Popover>
    );
}
