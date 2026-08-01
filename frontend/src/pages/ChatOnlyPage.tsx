import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ChatMessageList } from "@/components/chat/ChatMessageList";
import { ChatAgentSelector } from "@/components/chat-only/ChatAgentSelector";
import { ChatOnlyLayout } from "@/components/chat-only/ChatOnlyLayout";
import { getChatAgents, type ChatAgentItem } from "@/services/agentApi";
import { getConversation, getConversationsByAgent } from "@/services/chatApi";

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
  // Agent owning the open conversation, resolved on /ui/chat/<chatId> routes
  // where no ?agent= search param exists. Stays empty until known; failures
  // are ignored so the chat itself keeps working without the header chip.
  const [conversationAgent, setConversationAgent] = useState("");

  // Priority: explicit ?agent= param > open conversation's agent > the
  // single-agent shortcut (so single-agent users land straight in chat
  // without a selector flash; the effect below still syncs the param).
  const effectiveAgent =
    selectedAgent || conversationAgent || (agents.length === 1 ? agents[0].name : "");

  useEffect(() => {
    if (!chatId) {
      setConversationAgent("");
      return;
    }

    let cancelled = false;

    getConversation(chatId)
      .then((conversation) => {
        if (!cancelled) {
          setConversationAgent(conversation?.agent || "");
        }
      })
      .catch(() => {
        // Header chip stays hidden; the conversation view is unaffected.
      });

    return () => {
      cancelled = true;
    };
  }, [chatId]);

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
          try {
            const response = await getConversationsByAgent(agent.name, { limit: 1 });
            const latestId = response.data[0]?.id;
            return latestId ? ([agent.name, latestId] as const) : null;
          } catch (error) {
            // One agent's history being inaccessible must not hide the
            // "continue last chat" action for every other agent.
            console.error(`Error loading resume chat for agent ${agent.name}:`, error);
            return null;
          }
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
