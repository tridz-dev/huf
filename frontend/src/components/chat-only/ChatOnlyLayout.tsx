import { ReactNode } from "react";
import { ChatHeader } from "./ChatHeader";
import type { ChatAgentItem } from "@/services/agentApi";

interface ChatOnlyLayoutProps {
  agents?: ChatAgentItem[];
  currentAgentName?: string;
  children: ReactNode;
}

export function ChatOnlyLayout({ agents, currentAgentName, children }: ChatOnlyLayoutProps) {
  return (
    <div className="flex h-[100svh] min-h-0 flex-col overflow-hidden bg-paper-deep text-ink">
      <ChatHeader agents={agents} currentAgentName={currentAgentName} />
      <main className="min-h-0 flex-1 overflow-hidden">
        <div className="mx-auto h-full w-full max-w-5xl bg-panel shadow-sm md:my-4 md:h-[calc(100%-2rem)] md:overflow-hidden md:rounded-xl md:border md:border-line">
          {children}
        </div>
      </main>
    </div>
  );
}
