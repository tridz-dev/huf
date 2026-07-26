import { Check, ChevronDown, ChevronsUpDown, LayoutGrid, LogOut, Zap } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useUser } from "@/contexts/UserContext";
import UserAvatar from "@/components/UserAvatar";
import ChatAvatar from "@/components/chat/ChatAvatar";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { DEFAULT_AGENT_COLOR } from "@/data/color";
import { getInitials } from "@/utils/getInitials";
import type { ChatAgentItem } from "@/services/agentApi";

interface ChatHeaderProps {
  agents?: ChatAgentItem[];
  currentAgentName?: string;
}

export function ChatHeader({ agents = [], currentAgentName }: ChatHeaderProps) {
  const { logout, user } = useUser();
  const navigate = useNavigate();
  const displayName = user?.full_name || user?.name || "User";
  const displayEmail = user?.email || "";

  const currentAgent = agents.find((agent) => agent.name === currentAgentName);
  // Show the label once the agent is known, even if it is not in the user's
  // allowed agents list (the switcher below still requires list membership).
  const agentLabel = currentAgent?.agent_name || currentAgent?.name || currentAgentName;
  const showAgentSwitcher = agents.length > 1 && !!currentAgent;

  const openAgentChat = (agentName: string) => {
    navigate(`/ui/chat?agent=${encodeURIComponent(agentName)}`);
  };

  return (
    <header className="h-14 shrink-0 border-b border-zinc-200 bg-white/90 backdrop-blur supports-[backdrop-filter]:bg-white/75">
      <div className="mx-auto flex h-full w-full max-w-5xl items-center justify-between gap-3 px-3 sm:px-4">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <Zap className="size-4" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="truncate text-sm font-semibold text-zinc-950">HufAI</span>
              {showAgentSwitcher ? (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <button
                      type="button"
                      className="flex min-h-11 min-w-0 max-w-[140px] items-center gap-1 truncate rounded-full border border-zinc-200 px-3 text-xs text-zinc-600 transition-colors hover:bg-zinc-100 sm:max-w-[200px]"
                    >
                      <span className="truncate">{agentLabel}</span>
                      <ChevronDown className="size-3.5 shrink-0 text-zinc-400" />
                      <span className="sr-only">Switch assistant</span>
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="start" className="w-64">
                    <DropdownMenuLabel className="text-xs font-normal text-zinc-500">
                      Assistants
                    </DropdownMenuLabel>
                    {agents.map((agent) => (
                      <DropdownMenuItem
                        key={agent.name}
                        onClick={() => openAgentChat(agent.name)}
                        className="gap-2"
                      >
                        <ChatAvatar
                          variant="listing_ai"
                          color={agent.agent_color || DEFAULT_AGENT_COLOR}
                        >
                          {getInitials(agent.agent_name || agent.name)}
                        </ChatAvatar>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm">
                            {agent.agent_name || agent.name}
                          </span>
                          <span className="block truncate text-xs text-muted-foreground">
                            {agent.description || agent.model || "Chat agent"}
                          </span>
                        </span>
                        {agent.name === currentAgentName && (
                          <Check className="size-4 shrink-0 text-primary" />
                        )}
                      </DropdownMenuItem>
                    ))}
                    <DropdownMenuSeparator />
                    <DropdownMenuItem onClick={() => navigate("/ui/chat")}>
                      <LayoutGrid className="mr-2 size-4" />
                      All assistants
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              ) : (
                agentLabel && (
                  <span className="hidden max-w-[180px] truncate rounded-full border border-zinc-200 px-2 py-0.5 text-xs text-zinc-600 sm:inline">
                    {agentLabel}
                  </span>
                )
              )}
            </div>
            <p className="truncate text-xs text-zinc-500">Chat</p>
          </div>
        </div>

        {user && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" className="h-10 min-w-10 gap-2 px-2">
                <UserAvatar className="size-8 rounded-full" />
                <span className="hidden max-w-32 truncate text-sm font-medium sm:inline">
                  {displayName}
                </span>
                <ChevronsUpDown className="hidden size-4 text-zinc-500 sm:block" />
                <span className="sr-only">Open user menu</span>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-64">
              <DropdownMenuLabel className="font-normal">
                <div className="flex items-center gap-2">
                  <UserAvatar className="size-8 rounded-full" />
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{displayName}</p>
                    {displayEmail && (
                      <p className="truncate text-xs text-muted-foreground">{displayEmail}</p>
                    )}
                  </div>
                </div>
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={logout} className="text-red-500 focus:text-red-700">
                <LogOut className="mr-2 size-4" />
                Log out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>
    </header>
  );
}
