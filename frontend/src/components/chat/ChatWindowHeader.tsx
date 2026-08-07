import { useEffect, useState, type ReactNode } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Check, ChevronDown, PanelLeftOpen, PanelRight } from "lucide-react";
import { Button } from "../ui/button";
import { Popover, PopoverAnchor, PopoverContent, PopoverTrigger } from "../ui/popover";
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from "../ui/dropdown-menu";
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
    /** Whether the right-docked artifact preview pane is currently open. Drives
     * the toggle glyph's fill state (spec section 28). */
    artifactPaneOpen?: boolean;
    /** Toggles the artifact preview pane. The toggle button only renders when
     * this is provided, so the control is never present-but-inert. */
    onToggleArtifactPane?: () => void;
}

export function ChatWindowHeader({
    chatId: chatIdProp,
    onToggleSidebar,
    artifactPaneOpen,
    onToggleArtifactPane,
}: ChatWindowHeaderProps) {
    const { chatId: routeChatId } = useParams<{ chatId?: string }>();
    const [searchParams] = useSearchParams();
    const navigate = useNavigate();
    const chatId = chatIdProp ?? (routeChatId && routeChatId !== 'new' ? routeChatId : null);

    const [agent, setAgent] = useState<AgentDoc | null>(null);
    const [conversationModel, setConversationModel] = useState<string | null>(null);
    const [conversationTitle, setConversationTitle] = useState<string | null>(null);
    const [switcherOpen, setSwitcherOpen] = useState(false);
    const [dataPanelOpen, setDataPanelOpen] = useState(false);

    useEffect(() => {
        let cancelled = false;

        if (!chatId) {
            setConversationModel(null);
            setConversationTitle(null);
        }

        async function fetchAgentData() {
            try {
                let agentName: string | null = null;
                let model: string | null = null;
                let title: string | null = null;

                if (chatId) {
                    try {
                        const conversation = await getConversation(chatId);
                        if (conversation?.agent) {
                            agentName = conversation.agent;
                        }
                        if (conversation?.model) {
                            model = conversation.model;
                        }
                        if (conversation?.title) {
                            title = conversation.title;
                        }
                        if (!cancelled) {
                            setConversationModel(model);
                            setConversationTitle(title);
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

    const model = conversationModel || agent?.model;
    const showConversationData = !!chatId && agent?.enable_conversation_data === 1;

    if (!agent) {
        return (
            <header className="flex h-chat-header flex-none items-center gap-2.5 border-b border-paper-deep bg-panel px-4">
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
                <AgentSwitcher currentAgentName={null} triggerLabel="No agent selected" />
                <span className="flex-1" />
                <ArtifactPaneToggle open={artifactPaneOpen} onToggle={onToggleArtifactPane} />
            </header>
        );
    }

    return (
        <header className="flex h-chat-header flex-none items-center gap-2.5 border-b border-paper-deep bg-panel px-4">
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

            {/* The switcher popover has no trigger of its own here — it anchors to the
                title button and is opened by the "Switch agent" menu item below. */}
            <AgentSwitcher
                currentAgentName={agent.name}
                open={switcherOpen}
                onOpenChange={setSwitcherOpen}
            >
                <div className="flex min-w-0 items-center">
                    <DropdownMenu modal={false}>
                        <DropdownMenuTrigger asChild>
                            <button
                                type="button"
                                className="-mx-1 flex min-w-0 items-center gap-1 rounded-md px-1 py-0.5 hover:bg-paper-deep"
                            >
                                <span className="truncate text-[14px] font-[590] tracking-[-0.01em] text-ink">
                                    {conversationTitle || agent.agent_name}
                                </span>
                                <ChevronDown className="size-[14px] shrink-0 text-steel-soft" />
                            </button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="start" className="w-56">
                            <DropdownMenuItem onSelect={() => navigate(`/agents/${agent.name}`)}>
                                Open agent
                            </DropdownMenuItem>
                            <DropdownMenuItem
                                onSelect={() => {
                                    // Let the menu finish closing before handing focus over.
                                    setTimeout(() => setSwitcherOpen(true), 0);
                                }}
                            >
                                Switch agent
                            </DropdownMenuItem>
                            {showConversationData && (
                                <DropdownMenuItem
                                    onSelect={() => {
                                        setTimeout(() => setDataPanelOpen(true), 0);
                                    }}
                                >
                                    Conversation data
                                </DropdownMenuItem>
                            )}
                        </DropdownMenuContent>
                    </DropdownMenu>
                </div>
            </AgentSwitcher>

            {model && <span className="font-mono text-[11px] text-steel-soft">{model}</span>}

            <span className="flex-1" />

            {/* Rendered outside the dropdown: a Sheet must not live inside DropdownMenuContent. */}
            {showConversationData && chatId && (
                <ConversationDataPanel
                    conversationId={chatId}
                    canWrite={agent.conversation_data_api_permission === 'Write'}
                    open={dataPanelOpen}
                    onOpenChange={setDataPanelOpen}
                />
            )}

            <ArtifactPaneToggle open={artifactPaneOpen} onToggle={onToggleArtifactPane} />
        </header>
    );
}

interface ArtifactPaneToggleProps {
    open?: boolean;
    onToggle?: () => void;
}

/**
 * The artifact pane toggle glyph (spec section 28): a plain `PanelRight`
 * outline when closed, filled with full-contrast ink when open. Never a
 * vertical "Artifact" tab. Rendered only when `onToggle` is provided, so an
 * agent/conversation with no artifacts never shows an inert control.
 */
function ArtifactPaneToggle({ open, onToggle }: ArtifactPaneToggleProps) {
    if (!onToggle) return null;

    return (
        <Button
            type="button"
            variant="ghost"
            size="icon"
            className={open ? "h-8 w-8 text-ink hover:text-ink" : "h-8 w-8 text-steel hover:text-ink"}
            onClick={onToggle}
        >
            <PanelRight className={open ? "size-[17px] fill-current" : "size-[17px]"} />
            <span className="sr-only">{open ? "Hide artifacts" : "Show artifacts"}</span>
        </Button>
    );
}

interface AgentSwitcherProps {
    /** Name (doctype id) of the agent currently active in this chat window,
     * or null when no conversation/agent has been resolved yet. */
    currentAgentName: string | null;
    /** Label for the switcher's own trigger button. Omit to render no trigger — the
     * popover then anchors to `children` and is opened via `open`/`onOpenChange`. */
    triggerLabel?: string;
    /** Controlled open state, for callers that open the switcher from elsewhere. */
    open?: boolean;
    onOpenChange?: (open: boolean) => void;
    /** Anchor element, used when there is no `triggerLabel`. */
    children?: ReactNode;
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
function AgentSwitcher({
    currentAgentName,
    triggerLabel,
    open: openProp,
    onOpenChange,
    children,
}: AgentSwitcherProps) {
    const navigate = useNavigate();
    const [internalOpen, setInternalOpen] = useState(false);
    const open = openProp ?? internalOpen;
    const setOpen = (next: boolean) => {
        if (openProp === undefined) setInternalOpen(next);
        onOpenChange?.(next);
    };
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
            {triggerLabel !== undefined ? (
                <PopoverTrigger asChild>
                    <button
                        type="button"
                        className="flex items-center gap-1 rounded-md -mx-1 px-1 text-sm font-semibold text-ink hover:bg-paper-deep"
                    >
                        <span className="truncate max-w-[200px]">{triggerLabel}</span>
                        <ChevronDown className="w-3.5 h-3.5 shrink-0 text-steel-soft" />
                    </button>
                </PopoverTrigger>
            ) : (
                <PopoverAnchor asChild>{children}</PopoverAnchor>
            )}
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
