import { Bot, History, MessageSquarePlus } from "lucide-react";
import type { ReactNode } from "react";
import { useUser } from "@/contexts/UserContext";
import ChatAvatar from "@/components/chat/ChatAvatar";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { DEFAULT_AGENT_COLOR } from "@/data/color";
import { getFirstName } from "@/utils/getFirstName";
import { getInitials } from "@/utils/getInitials";
import type { ChatAgentItem } from "@/services/agentApi";

interface ChatAgentSelectorProps {
  agents: ChatAgentItem[];
  loading: boolean;
  error?: string | null;
  onSelectAgent: (agentName: string) => void;
  /** Map of agent name -> latest conversation id, for "Continue last chat". */
  resumeChats?: Record<string, string>;
  onResumeChat?: (chatId: string) => void;
}

export function ChatAgentSelector({
  agents,
  loading,
  error,
  onSelectAgent,
  resumeChats = {},
  onResumeChat,
}: ChatAgentSelectorProps) {
  const { user } = useUser();
  const firstName = getFirstName(user?.full_name || user?.name);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center px-5">
        <div className="w-full max-w-md space-y-3">
          <Skeleton className="mx-auto size-12 rounded-full" />
          <Skeleton className="mx-auto h-5 w-44" />
          <Skeleton className="mx-auto h-4 w-64" />
          <div className="space-y-2 pt-4">
            <Skeleton className="h-14 w-full rounded-xl" />
            <Skeleton className="h-14 w-full rounded-xl" />
            <Skeleton className="h-14 w-full rounded-xl" />
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <CenteredState
        icon={<Bot className="size-5" />}
        title="Chat is unavailable"
        description={error}
      />
    );
  }

  if (agents.length === 0) {
    return (
      <CenteredState
        icon={<Bot className="size-5" />}
        title="No chat access available"
        description="There are no enabled chat agents available for your account."
      />
    );
  }

  return (
    <div className="flex h-full items-center justify-center overflow-y-auto px-4 py-8">
      <div className="w-full max-w-lg space-y-6">
        <div className="space-y-2 text-center">
          <div className="mx-auto flex size-12 items-center justify-center rounded-full bg-primary/10 text-primary">
            <MessageSquarePlus className="size-5" />
          </div>
          <h1 className="text-xl font-semibold text-ink">
            {firstName ? `Hi ${firstName}, choose an assistant` : "Choose an assistant"}
          </h1>
          <p className="text-sm text-zinc-500">Start a focused chat with one of your available Huf agents.</p>
        </div>

        <div className="space-y-2">
          {agents.map((agent) => {
            const resumeChatId = resumeChats[agent.name];
            return (
              <div
                key={agent.name}
                className="flex items-center gap-1 rounded-xl border border-input bg-background pr-1 shadow-sm"
              >
                <Button
                  type="button"
                  variant="ghost"
                  className="h-auto min-w-0 flex-1 justify-start gap-3 rounded-xl px-4 py-3 text-left"
                  onClick={() => onSelectAgent(agent.name)}
                >
                  <ChatAvatar variant="listing_ai" color={agent.agent_color || DEFAULT_AGENT_COLOR}>
                    {getInitials(agent.agent_name || agent.name)}
                  </ChatAvatar>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-semibold text-zinc-900">
                      {agent.agent_name || agent.name}
                    </span>
                    {agent.description ? (
                      <span className="block truncate text-xs font-normal text-zinc-500">
                        {agent.description}
                      </span>
                    ) : (
                      <span className="block truncate text-xs font-normal text-zinc-500">
                        {agent.model || "Chat agent"}
                      </span>
                    )}
                  </span>
                </Button>
                {resumeChatId && onResumeChat && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="shrink-0 gap-1.5 text-xs text-zinc-500 hover:text-zinc-900"
                    onClick={() => onResumeChat(resumeChatId)}
                  >
                    <History className="size-3.5" />
                    <span className="hidden sm:inline">Continue last chat</span>
                    <span className="sm:hidden">Continue</span>
                  </Button>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function CenteredState({
  icon,
  title,
  description,
}: {
  icon: ReactNode;
  title: string;
  description: string;
}) {
  return (
    <div className="flex h-full items-center justify-center px-5 text-center">
      <div className="max-w-sm space-y-3">
        <div className="mx-auto flex size-12 items-center justify-center rounded-full bg-zinc-100 text-zinc-500">
          {icon}
        </div>
        <h1 className="text-lg font-semibold text-ink">{title}</h1>
        <p className="text-sm leading-6 text-zinc-500">{description}</p>
      </div>
    </div>
  );
}
