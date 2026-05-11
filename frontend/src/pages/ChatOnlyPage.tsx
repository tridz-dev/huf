import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ChatMessageList } from "@/components/chat/ChatMessageList";
import { ChatAgentSelector } from "@/components/chat-only/ChatAgentSelector";
import { ChatOnlyLayout } from "@/components/chat-only/ChatOnlyLayout";
import { getChatAgents, type ChatAgentItem } from "@/services/agentApi";

export default function ChatOnlyPage() {
  const navigate = useNavigate();
  const { chatId: routeChatId } = useParams<{ chatId?: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const chatId = routeChatId && routeChatId !== "new" ? routeChatId : null;
  const selectedAgent = searchParams.get("agent") || "";

  const [agents, setAgents] = useState<ChatAgentItem[]>([]);
  const [loadingAgents, setLoadingAgents] = useState(true);
  const [agentsError, setAgentsError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadAgents() {
      setLoadingAgents(true);
      setAgentsError(null);
      try {
        const nextAgents = await getChatAgents();
        if (!cancelled) {
          setAgents(nextAgents);
        }
      } catch (error) {
        if (!cancelled) {
          setAgentsError(error instanceof Error ? error.message : "Unable to load chat agents.");
        }
      } finally {
        if (!cancelled) {
          setLoadingAgents(false);
        }
      }
    }

    loadAgents();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (loadingAgents || chatId || selectedAgent || agents.length !== 1) {
      return;
    }

    setSearchParams({ agent: agents[0].name }, { replace: true });
  }, [agents, chatId, loadingAgents, selectedAgent, setSearchParams]);

  const currentAgent = useMemo(
    () => agents.find((agent) => agent.name === selectedAgent),
    [agents, selectedAgent]
  );

  const handleSelectAgent = useCallback(
    (agentName: string) => {
      navigate(`/ui/chat?agent=${encodeURIComponent(agentName)}`);
    },
    [navigate]
  );

  const handleConversationCreated = useCallback(
    (conversationId: string) => {
      navigate(`/ui/chat/${conversationId}`);
    },
    [navigate]
  );

  const getNewConversationPath = useCallback(
    (agentName: string) => `/ui/chat?agent=${encodeURIComponent(agentName)}`,
    []
  );

  const shouldShowSelector = !chatId && (!selectedAgent || (!loadingAgents && !currentAgent));

  return (
    <ChatOnlyLayout agentLabel={currentAgent?.agent_name}>
      {shouldShowSelector ? (
        <ChatAgentSelector
          agents={agents}
          loading={loadingAgents}
          error={agentsError}
          onSelectAgent={handleSelectAgent}
        />
      ) : (
        <div className="flex h-full min-h-0 flex-col overflow-hidden">
          <ChatMessageList
            chatId={chatId}
            onConversationCreated={handleConversationCreated}
            getNewConversationPath={getNewConversationPath}
          />
        </div>
      )}
    </ChatOnlyLayout>
  );
}
