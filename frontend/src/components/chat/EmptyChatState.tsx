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
        <div className="coldstart-header">
            <ChatAvatar
                variant="listing_ai"
                color={agentColor || DEFAULT_AGENT_COLOR}
                className="coldstart-avatar"
            >
                {getInitials(displayName)}
            </ChatAvatar>
            <div className="coldstart-name">{displayName}</div>
            {agentDescription && (
                <div className="coldstart-desc">{agentDescription}</div>
            )}
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
        <div className="starter-grid">
            {starterPrompts.slice(0, 3).map((prompt) => (
                <button
                    key={prompt.name || prompt.prompt_text}
                    type="button"
                    className="starter-btn"
                    onClick={() => onSendStarter(prompt.prompt_text)}
                >
                    {prompt.prompt_text}
                </button>
            ))}
        </div>
    );
}
