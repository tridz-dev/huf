import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import {
    ArrowLeft,
    BarChart3,
    Check,
    ChevronDown,
    MoreVertical,
    PanelLeft,
    PanelLeftOpen,
    Pencil,
    Plus,
    Search,
    Settings,
    Zap,
} from "lucide-react";
import { Button } from "../ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "../ui/popover";
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from "../ui/dropdown-menu";
import { cn } from "@/lib/utils";
import { getInitials } from "@/utils/getInitials";
import { getConversation } from "@/services/chatApi";
import { getAgent, getChatAgents, type ChatAgentItem } from "@/services/agentApi";
import type { AgentDoc } from "@/types/agent.types";
import { DEFAULT_AGENT_COLOR } from "@/data/color";
import { ConversationDataPanel } from "@/components/conversation/ConversationDataPanel";
import { DEFAULT_COLD_START_AGENT } from "./useChatAgentIdentity";
import { draftAutomationFromConversation } from "@/services/automationApi";

interface ChatWindowHeaderProps {
    chatId?: string | null;
    onToggleSidebar?: () => void;
    /** Whether the right-docked artifact preview pane is currently open. Drives
     * the toggle glyph's fill state (spec section 28). */
    artifactPaneOpen?: boolean;
    /** Toggles the artifact preview pane. The toggle button only renders when
     * this is provided, so the control is never present-but-inert. */
    onToggleArtifactPane?: () => void;
    /** Whether the right-docked conversation analytics pane is currently open.
     * Sibling of artifactPaneOpen - drives the analytics toggle's fill state. */
    analyticsPaneOpen?: boolean;
    /** Toggles the analytics pane. Sibling of onToggleArtifactPane: the
     * toggle button only renders when this is provided. */
    onToggleAnalyticsPane?: () => void;
    /** Whether the left rail is collapsed. When true, the header gains a
     * leading icon cluster (expand rail, Dashboard, New, divider) in place
     * of the plain sidebar-open button (spec 28.5). */
    railCollapsed?: boolean;
    /** Expands the collapsed rail. Only meaningful when `railCollapsed` is
     * true; supplied by the component that owns the rail's collapse state. */
    onExpandRail?: () => void;
}

export function ChatWindowHeader({
    chatId: chatIdProp,
    onToggleSidebar,
    artifactPaneOpen,
    onToggleArtifactPane,
    analyticsPaneOpen,
    onToggleAnalyticsPane,
    railCollapsed,
    onExpandRail,
}: ChatWindowHeaderProps) {
    const { chatId: routeChatId } = useParams<{ chatId?: string }>();
    const [searchParams] = useSearchParams();
    const navigate = useNavigate();
    const chatId = chatIdProp ?? (routeChatId && routeChatId !== 'new' ? routeChatId : null);

    const [agent, setAgent] = useState<AgentDoc | null>(null);
    const [conversationModel, setConversationModel] = useState<string | null>(null);
    const [conversationTitle, setConversationTitle] = useState<string | null>(null);
    // Spec §9/§22: switching agents starts a new conversation rather than
    // mutating this one - when the open conversation belongs to a Project,
    // that new conversation must inherit it. Tracked separately from the
    // model/title state above so `AgentSwitcher` can read it regardless of
    // whether `agent` has resolved yet.
    const [conversationProject, setConversationProject] = useState<string | null>(null);
    const [switcherOpen, setSwitcherOpen] = useState(false);
    const [dataPanelOpen, setDataPanelOpen] = useState(false);
    const [creatingAutomation, setCreatingAutomation] = useState(false);

    async function handleCreateAutomationFromChat() {
        if (!chatId || creatingAutomation) return;
        setCreatingAutomation(true);
        try {
            const draft = await draftAutomationFromConversation(chatId);
            if (!draft?.agent) return;
            // AutomationFormPage already reads `?agent=` to pre-select the
            // Agent on the create form; the rest (instruction, description)
            // is left for the user to fill in from what they just discussed
            // -- see huf.ai.automation_api.draft_automation_from_conversation.
            navigate(`/automations/new?agent=${encodeURIComponent(draft.agent)}`);
        } finally {
            setCreatingAutomation(false);
        }
    }

    useEffect(() => {
        let cancelled = false;

        if (!chatId) {
            setConversationModel(null);
            setConversationTitle(null);
            setConversationProject(null);
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
                            setConversationProject(conversation?.project ?? null);
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
                    agentName = searchParams.get('agent') ?? DEFAULT_COLD_START_AGENT;
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
    // For an existing conversation, use its own project. For a not-yet-
    // created chat, fall back to `?project=` so a Project's "+ New chat"
    // entry point (which lands here with that param already set) still
    // carries the project through an agent switch before any message
    // has been sent.
    const projectForSwitch = chatId ? conversationProject : searchParams.get('project');
    const showConversationData = !!chatId && agent?.enable_conversation_data === 1;

    // Spec 28.1 uses `padding: 0 16px`; the collapsed-rail row (28.5) is
    // `0 14px`. The extra icon cluster only appears when collapsed, so the
    // tighter padding is scoped to that state alone.
    const headerClassName = cn(
        "flex h-chat-header flex-none items-center gap-2.5 border-b border-paper-deep bg-panel",
        railCollapsed ? "px-[14px]" : "px-4",
    );

    if (!agent) {
        return (
            <header className={headerClassName}>
                {railCollapsed ? (
                    <CollapsedRailCluster onExpandRail={onExpandRail} navigate={navigate} />
                ) : (
                    showOpenSidebarBtn && (
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
                    )
                )}
                <AgentSwitcher currentAgentName={null} projectId={projectForSwitch} open={switcherOpen} onOpenChange={setSwitcherOpen}>
                    <button
                        type="button"
                        className="flex items-center gap-1 rounded-md -mx-1 px-1 text-sm font-semibold text-ink hover:bg-paper-deep"
                    >
                        <span className="truncate max-w-[200px]">No agent selected</span>
                        <ChevronDown className="w-3.5 h-3.5 shrink-0 text-steel-soft" />
                    </button>
                </AgentSwitcher>
                <span className="flex-1" />
                <AnalyticsPaneToggle open={analyticsPaneOpen} onToggle={onToggleAnalyticsPane} />
                <ArtifactPaneToggle open={artifactPaneOpen} onToggle={onToggleArtifactPane} />
            </header>
        );
    }

    // Spec 28.2: with the artifact pane (or the sibling analytics pane) open,
    // the header simplifies down to the title, a flex spacer, and the pane
    // toggles — the picker chevron, model text, and overflow dots all drop out.
    if (artifactPaneOpen || analyticsPaneOpen) {
        return (
            <header className={headerClassName}>
                <span className="truncate text-[14px] font-[590] tracking-[-0.01em] text-ink">
                    {conversationTitle || agent.agent_name}
                </span>
                <span className="flex-1" />
                <AnalyticsPaneToggle open={analyticsPaneOpen} onToggle={onToggleAnalyticsPane} />
                <ArtifactPaneToggle open={artifactPaneOpen} onToggle={onToggleArtifactPane} />
            </header>
        );
    }

    return (
        <header className={headerClassName}>
            {railCollapsed ? (
                <CollapsedRailCluster onExpandRail={onExpandRail} navigate={navigate} />
            ) : (
                showOpenSidebarBtn && (
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
                )
            )}

            {/* Spec 28.4: the title chevron opens the picker itself, not a two-item
                menu. Switching stays in the conversation; settings navigates away —
                those two different outcomes never share a menu (see the overflow
                menu below for the navigate-away actions). */}
            <AgentSwitcher currentAgentName={agent.name} projectId={projectForSwitch} open={switcherOpen} onOpenChange={setSwitcherOpen}>
                <button
                    type="button"
                    className="-mx-1 flex min-w-0 items-center gap-1 rounded-md px-1 py-0.5 hover:bg-paper-deep"
                >
                    <span className="truncate text-[14px] font-[590] tracking-[-0.01em] text-ink">
                        {conversationTitle || agent.agent_name}
                    </span>
                    <ChevronDown className="size-[14px] shrink-0 text-steel-soft" />
                </button>
            </AgentSwitcher>

            {model && <span className="font-mono text-[11px] text-steel-soft">{model}</span>}

            <span className="flex-1" />

            <DropdownMenu modal={false}>
                <DropdownMenuTrigger asChild>
                    <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-steel hover:text-ink"
                    >
                        <MoreVertical className="size-4" />
                        <span className="sr-only">Conversation actions</span>
                    </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-[230px] px-0 py-[5px]">
                    <DropdownMenuItem
                        onSelect={() => navigate(`/agents/${agent.name}`)}
                        className="h-[30px] gap-[9px] px-3 py-0 text-[13px]"
                    >
                        <Settings className="size-[15px]" />
                        Agent settings
                    </DropdownMenuItem>
                    {chatId && (
                        <DropdownMenuItem
                            onSelect={() => {
                                window.dispatchEvent(
                                    new CustomEvent('huf:conversation-rename-request', {
                                        detail: { conversationId: chatId },
                                    })
                                );
                            }}
                            className="h-[30px] gap-[9px] px-3 py-0 text-[13px]"
                        >
                            <Pencil className="size-[15px]" />
                            Rename
                        </DropdownMenuItem>
                    )}
                    {showConversationData && (
                        <DropdownMenuItem
                            onSelect={() => {
                                // Let the menu finish closing before opening the sheet.
                                setTimeout(() => setDataPanelOpen(true), 0);
                            }}
                            className="h-[30px] gap-[9px] px-3 py-0 text-[13px]"
                        >
                            Conversation data
                        </DropdownMenuItem>
                    )}
                    {chatId && (
                        <DropdownMenuItem
                            disabled={creatingAutomation}
                            onSelect={() => {
                                void handleCreateAutomationFromChat();
                            }}
                            className="h-[30px] gap-[9px] px-3 py-0 text-[13px]"
                        >
                            <Zap className="size-[15px]" />
                            Create automation from this chat
                        </DropdownMenuItem>
                    )}
                </DropdownMenuContent>
            </DropdownMenu>

            {/* Rendered outside the dropdown: a Sheet must not live inside DropdownMenuContent. */}
            {showConversationData && chatId && (
                <ConversationDataPanel
                    conversationId={chatId}
                    canWrite={agent.conversation_data_api_permission === 'Write'}
                    open={dataPanelOpen}
                    onOpenChange={setDataPanelOpen}
                />
            )}

            <AnalyticsPaneToggle open={analyticsPaneOpen} onToggle={onToggleAnalyticsPane} />
            <ArtifactPaneToggle open={artifactPaneOpen} onToggle={onToggleArtifactPane} />
        </header>
    );
}

interface CollapsedRailClusterProps {
    onExpandRail?: () => void;
    navigate: ReturnType<typeof useNavigate>;
}

/**
 * Spec 28.5: leading icon cluster shown as the first item in the 40px header
 * row when the rail is collapsed — expand rail, Dashboard, New, then a
 * divider before the rest of the header. The spec's prose also lists a
 * Search icon here; it is deliberately omitted because conversation search
 * does not exist in this product yet.
 */
function CollapsedRailCluster({ onExpandRail, navigate }: CollapsedRailClusterProps) {
    return (
        <>
            <button
                type="button"
                onClick={onExpandRail}
                className="flex-none text-steel hover:text-ink"
            >
                <PanelLeft className="size-[17px]" />
                <span className="sr-only">Expand sidebar</span>
            </button>
            <button
                type="button"
                onClick={() => navigate('/')}
                className="flex-none text-steel hover:text-ink"
            >
                <ArrowLeft className="size-[17px]" />
                <span className="sr-only">Dashboard</span>
            </button>
            <button
                type="button"
                onClick={() => navigate('/chat/new')}
                className="flex-none text-steel hover:text-ink"
            >
                <Plus className="size-[17px]" />
                <span className="sr-only">New chat</span>
            </button>
            <span className="h-4 w-px bg-line" />
        </>
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
            {/* Lucide's PanelRight is a stroke-only outline: its <rect> carries no
                fill attribute, so `fill-current` floods the WHOLE square and the
                glyph stops reading as a panel at all. The spec's filled variant
                fills only the right column, so that column is drawn explicitly. */}
            <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
                className="size-[17px]"
                aria-hidden="true"
            >
                <rect x="3" y="3" width="18" height="18" rx="2" />
                <path d="M15 3v18" />
                {open && (
                    <path
                        d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4z"
                        fill="currentColor"
                        stroke="none"
                    />
                )}
            </svg>
            <span className="sr-only">{open ? "Hide artifacts" : "Show artifacts"}</span>
        </Button>
    );
}

interface AnalyticsPaneToggleProps {
    open?: boolean;
    onToggle?: () => void;
}

/**
 * Sibling of `ArtifactPaneToggle`, following its exact shape: ghost icon
 * button, `h-8 w-8`, `text-steel hover:text-ink` when closed / `text-ink`
 * when open, rendered only when `onToggle` is provided so a conversation
 * with no analytics available never shows an inert control.
 */
function AnalyticsPaneToggle({ open, onToggle }: AnalyticsPaneToggleProps) {
    if (!onToggle) return null;

    return (
        <Button
            type="button"
            variant="ghost"
            size="icon"
            className={open ? "h-8 w-8 text-ink hover:text-ink" : "h-8 w-8 text-steel hover:text-ink"}
            onClick={onToggle}
        >
            <BarChart3 className="size-[17px]" strokeWidth={open ? 2.25 : 2} aria-hidden="true" />
            <span className="sr-only">{open ? "Hide analytics" : "Show analytics"}</span>
        </Button>
    );
}

interface AgentSwitcherProps {
    /** Name (doctype id) of the agent currently active in this chat window,
     * or null when no conversation/agent has been resolved yet. */
    currentAgentName: string | null;
    /** HUF Project the resulting new conversation should inherit (spec
     * §9/§22: agent switching never mutates the open conversation, but a
     * switch made from inside a Project must still land in that Project). */
    projectId?: string | null;
    open: boolean;
    onOpenChange: (open: boolean) => void;
    /** Trigger element the popover anchors to and opens from (wrapped `asChild`). */
    children: ReactNode;
}

/** Local-provider name match. There is no "is local" flag on the provider
 * doctype, so this is a heuristic on the provider's display name. */
const LOCAL_PROVIDER_PATTERN = /ollama|local|lm ?studio/i;

interface AgentProviderGroup {
    provider: string;
    agents: ChatAgentItem[];
}

/** Groups agents by provider, local providers first (see
 * `LOCAL_PROVIDER_PATTERN`), then the rest alphabetically. */
function groupAgentsByProvider(agents: ChatAgentItem[]): AgentProviderGroup[] {
    const byProvider = new Map<string, ChatAgentItem[]>();
    for (const agentItem of agents) {
        const provider = agentItem.provider || "Other";
        const bucket = byProvider.get(provider);
        if (bucket) {
            bucket.push(agentItem);
        } else {
            byProvider.set(provider, [agentItem]);
        }
    }

    const providers = Array.from(byProvider.keys());
    providers.sort((a, b) => {
        const aLocal = LOCAL_PROVIDER_PATTERN.test(a);
        const bLocal = LOCAL_PROVIDER_PATTERN.test(b);
        if (aLocal !== bLocal) return aLocal ? -1 : 1;
        return a.localeCompare(b);
    });

    return providers.map((provider) => ({ provider, agents: byProvider.get(provider) ?? [] }));
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
    projectId,
    open,
    onOpenChange,
    children,
}: AgentSwitcherProps) {
    const navigate = useNavigate();
    const [agents, setAgents] = useState<ChatAgentItem[]>([]);
    const [loading, setLoading] = useState(false);
    const [search, setSearch] = useState("");

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

    // Reset the search box each time the picker opens rather than leaving a
    // stale query behind from the last time it was used.
    useEffect(() => {
        if (open) setSearch("");
    }, [open]);

    const handleSelect = (agentName: string) => {
        onOpenChange(false);
        const query = new URLSearchParams({ agent: agentName });
        if (projectId) query.set('project', projectId);
        navigate(`/chat?${query.toString()}`);
    };

    const filteredAgents = useMemo(() => {
        const query = search.trim().toLowerCase();
        if (!query) return agents;
        return agents.filter((agentItem) => {
            const name = (agentItem.agent_name || agentItem.name).toLowerCase();
            const model = (agentItem.model || "").toLowerCase();
            return name.includes(query) || model.includes(query);
        });
    }, [agents, search]);

    const groups = useMemo(() => groupAgentsByProvider(filteredAgents), [filteredAgents]);

    return (
        <Popover open={open} onOpenChange={onOpenChange}>
            <PopoverTrigger asChild>{children}</PopoverTrigger>
            <PopoverContent
                align="start"
                className="w-[300px] rounded-[12px] border-input p-0 shadow-lg"
            >
                <div className="border-b border-paper-deep p-2">
                    {/* 8px, not rounded-lg: --r-lg is 14px here, which reads as a pill
                        at 28px tall. Spec 28.4 draws a rounded rectangle. */}
                    <div className="flex h-7 items-center gap-[7px] rounded-[8px] bg-paper-deep px-[9px]">
                        <Search className="size-[14px] shrink-0 text-steel-soft" />
                        <input
                            value={search}
                            onChange={(event) => setSearch(event.target.value)}
                            placeholder="Search agents"
                            className="w-full min-w-0 bg-transparent text-[13px] text-ink outline-none placeholder:text-steel-soft"
                        />
                    </div>
                </div>
                {loading ? (
                    <div className="px-3 py-3 text-center text-[13px] text-steel">Loading agents...</div>
                ) : groups.length === 0 ? (
                    <div className="px-3 py-3 text-center text-[13px] text-steel">No chat agents available.</div>
                ) : (
                    <div className="max-h-80 overflow-y-auto pt-1 pb-1.5">
                        {groups.map((group, groupIndex) => (
                            <div key={group.provider}>
                                <div
                                    className={
                                        groupIndex > 0
                                            ? "mt-1 flex h-[22px] items-center px-3 font-mono text-[10px] uppercase tracking-[0.04em] text-steel-soft"
                                            : "flex h-[22px] items-center px-3 font-mono text-[10px] uppercase tracking-[0.04em] text-steel-soft"
                                    }
                                >
                                    {group.provider}
                                </div>
                                {group.agents.map((agentItem) => {
                                    const isCurrent = agentItem.name === currentAgentName;
                                    const hasModel = !!agentItem.model;
                                    return (
                                        <button
                                            key={agentItem.name}
                                            type="button"
                                            onClick={() => handleSelect(agentItem.name)}
                                            className={
                                                (isCurrent ? "bg-paper-deep " : "hover:bg-paper-deep ") +
                                                (hasModel ? "" : "opacity-55 ") +
                                                "flex h-[34px] items-center gap-[9px] px-3 text-left"
                                            }
                                        >
                                            <span
                                                className="flex h-5 w-5 flex-none items-center justify-center rounded-[6px] text-[9px] text-white"
                                                style={{ backgroundColor: agentItem.agent_color || DEFAULT_AGENT_COLOR }}
                                            >
                                                {getInitials(agentItem.agent_name || agentItem.name)}
                                            </span>
                                            <span className="min-w-0 flex-1 truncate text-[13px]">
                                                {agentItem.agent_name || agentItem.name}
                                                {agentItem.model && (
                                                    <span className="font-mono text-[11px] text-steel-soft"> {agentItem.model}</span>
                                                )}
                                            </span>
                                            {isCurrent && <Check className="size-[15px] shrink-0 text-ink" />}
                                        </button>
                                    );
                                })}
                            </div>
                        ))}
                    </div>
                )}
            </PopoverContent>
        </Popover>
    );
}
