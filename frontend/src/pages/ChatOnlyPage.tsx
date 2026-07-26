import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ChatMessageList } from "@/components/chat/ChatMessageList";
import { ChatAgentSelector } from "@/components/chat-only/ChatAgentSelector";
import { ChatOnlyLayout } from "@/components/chat-only/ChatOnlyLayout";
import { getChatAgents, type ChatAgentItem } from "@/services/agentApi";
import { getConversationsByAgent } from "@/services/chatApi";

export default function ChatOnlyPage() {
  const navigate = useNavigate();
  const { chatId: routeChatId } = useParams<{ chatId?: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const chatId = routeChatId && routeChatId !== "new" ? routeChatId : null;
  const selectedAgent = searchParams.get("agent") || "";

  const [agents, setAgents] = useState<ChatAgentItem[]>([]);
  const [loadingAgents, setLoadingAgents] = useState(true);
  const [agentsError, setAgentsError] = useState<string | null>(null);
  // Map of agent name -> latest conversation id, used for "Continue last chat"
  // on the multi-agent landing. Loaded lazily after agents resolve.
  const [resumeChats, setResumeChats] = useState<Record<string, string>>({});

  // When exactly one chat agent exists, treat it as selected immediately so
  // single-agent users land straight in chat without a selector flash; the
  // effect below still syncs the ?agent= search param.
  const effectiveAgent = selectedAgent || (agents.length === 1 ? agents[0].name : "");

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

  // Fetch the latest conversation per agent so the landing can offer
  // "Continue last chat". Only worth the extra calls when there is a
  // multi-agent landing to show; failures just leave the action hidden.
  useEffect(() => {
    if (loadingAgents || agents.length < 2) {
      setResumeChats({});
      return;
    }

    let cancelled = false;

    async function loadResumeChats() {
      const entries = await Promise.all(
        agents.map(async (agent) => {
          const response = await getConversationsByAgent(agent.name, { limit: 1 });
          const latestId = response.data[0]?.id;
          return latestId ? ([agent.name, latestId] as const) : null;
        })
      );

      if (!cancelled) {
        setResumeChats(
          Object.fromEntries(
            entries.filter((entry): entry is readonly [string, string] => entry !== null)
          )
        );
      }
    }

    loadResumeChats();

    return () => {
      cancelled = true;
    };
  }, [agents, loadingAgents]);

  const currentAgent = useMemo(
    () => agents.find((agent) => agent.name === effectiveAgent),
    [agents, effectiveAgent]
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

  const shouldShowSelector = !chatId && (!effectiveAgent || (!loadingAgents && !currentAgent));

  return (
    <ChatOnlyLayout agents={agents} currentAgentName={effectiveAgent}>
      {shouldShowSelector ? (
        <ChatAgentSelector
          agents={agents}
          loading={loadingAgents}
          error={agentsError}
          onSelectAgent={handleSelectAgent}
          resumeChats={resumeChats}
          onResumeChat={handleConversationCreated}
        />
      ) : (
        <div className="flex h-full min-h-0 flex-col overflow-hidden">
          <ChatMessageList
            key={chatId ?? effectiveAgent}
            chatId={chatId}
            onConversationCreated={handleConversationCreated}
            getNewConversationPath={getNewConversationPath}
          />
        </div>
      )}
    </ChatOnlyLayout>
  );
}
