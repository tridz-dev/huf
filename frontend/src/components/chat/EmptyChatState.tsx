import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../ui/button';
import { Skeleton } from '../ui/skeleton';
import ChatAvatar from './ChatAvatar';
import { getInitials } from '@/utils/getInitials';
import { getAgentsWithConversationCounts, type AgentWithCount } from '@/services/chatApi';
import { AgentModelSelector } from './AgentModelSelector';
import { DEFAULT_AGENT_COLOR } from '@/data/color';

export function EmptyChatState() {
    const navigate = useNavigate();
    const [recentAgents, setRecentAgents] = useState<AgentWithCount[]>([]);
    const [loadingAgents, setLoadingAgents] = useState(true);
    const [selectedAgent, setSelectedAgent] = useState<string>('');

    // Fetch recently used agents
    useEffect(() => {
        let cancelled = false;

        async function fetchRecentAgents() {
            setLoadingAgents(true);
            try {
                const agents = await getAgentsWithConversationCounts();
                if (!cancelled) {
                    // Get top 5 recently used agents
                    setRecentAgents(agents.slice(0, 5));
                }
            } catch (error) {
                console.error('Error fetching recent agents:', error);
            } finally {
                if (!cancelled) {
                    setLoadingAgents(false);
                }
            }
        }

        fetchRecentAgents();

        return () => {
            cancelled = true;
        };
    }, []);

    const handleAgentSelect = useCallback((agentId: string) => {
        setSelectedAgent(agentId);
        navigate(`/chat/new?agent=${agentId}`);
    }, [navigate]);

    const handleRecentAgentClick = useCallback((agentName: string) => {
        navigate(`/chat/new?agent=${agentName}`);
    }, [navigate]);

    return (
        <div className="flex-1 flex items-center justify-center">
            <div className="text-center space-y-6 max-w-md w-full px-6">
                <div className="space-y-2">
                    <p className="text-sm text-muted-foreground">Select an agent to start chatting</p>
                    <div className="flex justify-center">
                        <AgentModelSelector
                            value={selectedAgent}
                            onValueChange={handleAgentSelect}
                            showLabel={true}
                        />
                    </div>
                </div>
                
                {recentAgents.length > 0 && (
                    <div className="space-y-3">
                        <p className="text-xs font-medium text-zinc-500 uppercase tracking-wider">
                            Recently used agents
                        </p>
                        <div className="flex flex-wrap gap-2 justify-center">
                            {loadingAgents ? (
                                Array.from({ length: 6 }).map((_, i) => (
                                    <Skeleton key={i} className="h-10 w-24 rounded-lg" />
                                ))
                            ) : (
                                recentAgents.map((agent) => (
                                    <Button
                                        key={agent.name}
                                        variant="outline"
                                        size="sm"
                                        onClick={() => handleRecentAgentClick(agent.name)}
                                        className="gap-2 hover:bg-zinc-100"
                                    >
                                        <ChatAvatar 
                                            variant="listing_ai" 
                                            color={agent.agent_color || DEFAULT_AGENT_COLOR}
                                        >
                                            {getInitials(agent.agent_name)}
                                        </ChatAvatar>
                                        <span className="text-xs font-medium text-zinc-700">
                                            {agent.agent_name}
                                        </span>
                                    </Button>
                                ))
                            )}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
