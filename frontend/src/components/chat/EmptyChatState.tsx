import ChatAvatar from './ChatAvatar';
import { getInitials } from '@/utils/getInitials';
import { DEFAULT_AGENT_COLOR } from '@/data/color';
import type { AgentStarterPromptRow } from '@/types/agent.types';

interface EmptyChatStateProps {
    agentName: string;
    agentDisplayName: string;
    agentDescription: string;
    agentColor: string | null;
    starterPrompts: AgentStarterPromptRow[];
    onSendStarter: (text: string) => void;
}

export function EmptyChatState({
    agentName,
    agentDisplayName,
    agentDescription,
    agentColor,
    starterPrompts,
    onSendStarter,
}: EmptyChatStateProps) {
    const displayName = agentDisplayName || agentName;

    return (
        <div>
            <div className="coldstart-header">
                <ChatAvatar
                    variant="listing_ai"
                    color={agentColor || DEFAULT_AGENT_COLOR}
                    className="coldstart-avatar"
                >
                    {getInitials(displayName)}
                </ChatAvatar>
                <div className="min-w-0">
                    <div className="coldstart-name">{displayName}</div>
                    {agentDescription && (
                        <div className="coldstart-desc">{agentDescription}</div>
                    )}
                </div>
            </div>
            {starterPrompts.length > 0 && (
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
            )}
        </div>
    );
}
