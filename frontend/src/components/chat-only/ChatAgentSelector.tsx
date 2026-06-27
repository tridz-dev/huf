import { Bot, MessageSquarePlus } from "lucide-react";
import type { ReactNode } from "react";
import ChatAvatar from "@/components/chat/ChatAvatar";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { DEFAULT_AGENT_COLOR } from "@/data/color";
import { getInitials } from "@/utils/getInitials";
import type { ChatAgentItem } from "@/services/agentApi";

interface ChatAgentSelectorProps {
  agents: ChatAgentItem[];
  loading: boolean;
  error?: string | null;
  onSelectAgent: (agentName: string) => void;
}

export function ChatAgentSelector({
  agents,
  loading,
  error,
  onSelectAgent,
}: ChatAgentSelectorProps) {
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
          <h1 className="text-xl font-semibold text-zinc-950">Choose an assistant</h1>
          <p className="text-sm text-zinc-500">Start a focused chat with one of your available Huf agents.</p>
        </div>

        <div className="space-y-2">
          {agents.map((agent) => (
            <Button
              key={agent.name}
              type="button"
              variant="outline"
              className="h-auto w-full justify-start gap-3 rounded-xl px-4 py-3 text-left"
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
          ))}
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
        <h1 className="text-lg font-semibold text-zinc-950">{title}</h1>
        <p className="text-sm leading-6 text-zinc-500">{description}</p>
      </div>
    </div>
  );
}
