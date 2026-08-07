import { MessageSquare } from 'lucide-react';
import ChatAvatar from './ChatAvatar';
import { getInitials } from '@/utils/getInitials';
import { DEFAULT_AGENT_COLOR } from '@/data/color';
import type { AgentStarterPromptRow } from '@/types/agent.types';

interface ColdStartHeroProps {
    agentName: string;
    agentDisplayName: string;
    agentDescription: string;
    agentColor: string | null;
}

export function ColdStartHero({
    agentName,
    agentDisplayName,
    agentDescription,
    agentColor,
}: ColdStartHeroProps) {
    const displayName = agentDisplayName || agentName;

    return (
        <div className="flex items-center gap-[11px]">
            <ChatAvatar
                variant="listing_ai"
                color={agentColor || DEFAULT_AGENT_COLOR}
                className="h-[34px] w-[34px] rounded-full text-[12px] font-medium"
            >
                {getInitials(displayName)}
            </ChatAvatar>
            <div className="flex flex-col gap-px">
                <div className="text-[17px] font-semibold tracking-[-0.015em]">{displayName}</div>
                {agentDescription && (
                    <div className="text-[12px] text-steel">{agentDescription}</div>
                )}
            </div>
        </div>
    );
}

interface StarterPromptGridProps {
    starterPrompts: AgentStarterPromptRow[];
    onSendStarter: (text: string) => void;
}

export function StarterPromptGrid({
    starterPrompts,
    onSendStarter,
}: StarterPromptGridProps) {
    if (starterPrompts.length === 0) return null;

    return (
        <div className="flex flex-col gap-1.5">
            <div className="text-[11px] text-steel-soft">Try</div>
            <div className="flex flex-col gap-[5px]">
                {starterPrompts.slice(0, 3).map((prompt) => (
                    <button
                        key={prompt.name || prompt.prompt_text}
                        type="button"
                        className="flex h-8 items-center gap-[9px] rounded-[9px] border border-line px-[11px] text-[13px] text-left hover:bg-paper"
                        onClick={() => onSendStarter(prompt.prompt_text)}
                    >
                        <MessageSquare className="h-[15px] w-[15px] shrink-0 text-steel-soft" />
                        <span className="truncate">{prompt.prompt_text}</span>
                    </button>
                ))}
            </div>
        </div>
    );
}
