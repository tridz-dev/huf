import { useEffect, useLayoutEffect, useState, useCallback, useRef, useMemo } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { getConversationMessages, createAgentRunFeedback, getConversation, type ChatMessage } from "@/services/chatApi";
import { getAgent } from "@/services/agentApi";
import { useInfiniteScroll } from "@/hooks/useInfiniteScroll";
import { useChatSocket, type ToolCallEvent, type NewAgentMessageEvent, type AgentRunStatusEvent, type ConversationTitleUpdatedEvent } from '@/hooks/useChatSocket';
import { ChatMessage as ChatMessageComponent } from './ChatMessage';
import { ChatInput } from './ChatInput';
import { EmptyChatState } from './EmptyChatState';
import type { MessageType } from './types';
import type { LoadingType } from './ChatInput';
import { useChatAgentIdentity } from './useChatAgentIdentity';
import { useChatScrollToBottom } from './useChatScrollToBottom';
import { useRunStatusPolling } from './useRunStatusPolling';
import { usePendingRunHydration } from './usePendingRunHydration';
import {
    dispatchConversationTitleUpdated,
    useConversationTitlePostSuccessFallback,
} from './useConversationTitleFallback';
import {
    filterMessagesForConversation,
    hasStaleConversationItems,
    mergeConversationItemsIntoMessages,
    upsertAgentMessageFromSocket,
    upsertAgentRunStatusFromSocket,
    upsertToolUpdateFromSocket,
} from './chatMessageList.mappers';

interface ChatMessageListProps {
    chatId?: string | null;
    onConversationCreated?: (conversationId: string, agentName?: string) => void;
    getNewConversationPath?: (agentName: string) => string;
}

export function ChatMessageList({ 
    chatId: chatIdProp, 
    onConversationCreated,
    getNewConversationPath,
}: ChatMessageListProps) {
    const { chatId: routeChatId } = useParams<{ chatId?: string }>();
    const [searchParams] = useSearchParams();
    const chatId = chatIdProp ?? (routeChatId && routeChatId !== 'new' ? routeChatId : null);
    const isNewChat = !chatId;
    
    const [messages, setMessages] = useState<MessageType[]>([]);
    const [status, setStatus] = useState<'submitted' | 'streaming' | 'ready' | 'error'>('ready');
    const [loadingType, setLoadingType] = useState<LoadingType>('default');
    const isCreatingConversationRef = useRef(false);
    const newlyCreatedConversationIdRef = useRef<string | null>(null);
    const [isModelMismatch, setIsModelMismatch] = useState(false);
    const [isTransitioningToNewConversation, setIsTransitioningToNewConversation] = useState(false);
    const [conversationTitle, setConversationTitle] = useState<string | null>(null);
    const [runSucceeded, setRunSucceeded] = useState(false);

    const { agentName, agentColor, showToolExecutionDetails, allowFileUpload, maxUploadSizeMb, runImmediately, autonamingOfConversationTitle } = useChatAgentIdentity(chatId, searchParams);

    // Check for model mismatch between conversation and agent
    useEffect(() => {
        if (!chatId || !agentName) {
            setIsModelMismatch(false);
            return;
        }

        let cancelled = false;

        async function checkModelMismatch() {
            try {
                const [conversation, agent] = await Promise.all([
                    getConversation(chatId!),
                    getAgent(agentName),
                ]);

                if (cancelled) return;

                if (conversation?.model && agent?.model) {
                    setIsModelMismatch(conversation.model !== agent.model);
                } else {
                    setIsModelMismatch(false);
                }
            } catch (error) {
                console.error('Error checking model mismatch:', error);
                if (!cancelled) {
                    setIsModelMismatch(false);
                }
            }
        }

        checkModelMismatch();

        return () => {
            cancelled = true;
        };
    }, [chatId, agentName]);

    useEffect(() => {
        if (!chatId) {
            setConversationTitle(null);
            setRunSucceeded(false);
            return;
        }

        let cancelled = false;

        getConversation(chatId)
            .then((conversation) => {
                if (!cancelled) {
                    setConversationTitle(conversation?.title ?? null);
                }
            })
            .catch(() => {
                if (!cancelled) {
                    setConversationTitle(null);
                }
            });

        return () => {
            cancelled = true;
        };
    }, [chatId]);

    // Memoize initialParams to ensure stable reference but detect chatId changes
    const initialParams = useMemo(() => {
        return chatId ? { conversation: chatId } : {};
    }, [chatId]);

    // Don't fetch messages if we're transitioning to a newly created conversation
    // Use state-based check for reliable reactivity
    const shouldFetchMessages = useMemo(() => {
        return Boolean(chatId) && !isTransitioningToNewConversation;
    }, [chatId, isTransitioningToNewConversation]);

    // Enable fetching after transition period (when ref is cleared)
    useEffect(() => {
        if (chatId && newlyCreatedConversationIdRef.current === chatId) {
            // We're transitioning to a newly created conversation
            setIsTransitioningToNewConversation(true);
            
            // Enable fetching after a delay to allow navigation to complete
            // Use a longer delay to ensure messages are already displayed
            const timeoutId = setTimeout(() => {
                setIsTransitioningToNewConversation(false);
            }, 800);
            
            return () => clearTimeout(timeoutId);
        } else if (chatId && newlyCreatedConversationIdRef.current !== chatId) {
            // Not transitioning to new conversation, ensure fetching is enabled
            setIsTransitioningToNewConversation(false);
        }
    }, [chatId]);

    // Fetch messages
    const {
        items: conversationItems,
        initialLoading,
        loadingMore,
        hasMore,
        sentinelRef,
        error: messagesError,
    } = useInfiniteScroll<
        { limit?: number; start?: number },
        ChatMessage
    >({
        fetchFn: async (params) => {
            if (!chatId) {
                return { data: [], hasMore: false };
            }
            const response = await getConversationMessages({
                conversation: chatId,
                limit: params.limit || 20,
                start: params.start || 0,
            });
            return {
                data: response.data,
                hasMore: response.hasMore,
            };
        },
        initialParams: initialParams as any,
        pageSize: 20,
        direction: 'reverse',
        enabled: shouldFetchMessages,
        autoLoad: shouldFetchMessages,
        autoLoadMore: shouldFetchMessages,
    });

    // Handle tool updates from socket
    const handleToolUpdate = useCallback((event: ToolCallEvent) => {
        if (event.conversation_id !== chatId) return;
        setMessages((prev) => upsertToolUpdateFromSocket(prev, event));
    }, [chatId]);

    // Handle new agent message events (e.g., Image messages)
    const handleNewMessage = useCallback((event: NewAgentMessageEvent) => {
        if (event.conversation_id !== chatId) return;
        setMessages((prev) => upsertAgentMessageFromSocket(prev, event));
    }, [chatId]);

    // Handle queued agent run lifecycle events
    const handleAgentRunStatus = useCallback((event: AgentRunStatusEvent) => {
        if (event.conversation_id !== chatId) return;
        if (event.status === 'Success') {
            setRunSucceeded(true);
        }
        setMessages((prev) => upsertAgentRunStatusFromSocket(prev, event));
    }, [chatId]);

    const handleConversationTitleUpdated = useCallback((event: ConversationTitleUpdatedEvent) => {
        if (event.conversation_id !== chatId) return;
        setConversationTitle(event.title);
        setRunSucceeded(false);
        dispatchConversationTitleUpdated({
            conversationId: event.conversation_id,
            title: event.title,
            animate: true,
        });
    }, [chatId]);

    useChatSocket({
        conversationId: chatId,
        onToolUpdate: handleToolUpdate,
        onNewMessage: handleNewMessage,
        onAgentRunStatus: handleAgentRunStatus,
        onConversationTitleUpdated: handleConversationTitleUpdated,
    });

    useConversationTitlePostSuccessFallback({
        conversationId: chatId,
        currentTitle: conversationTitle,
        autonamingEnabled: autonamingOfConversationTitle,
        runSucceeded,
    });

    // Polling fallback: a missed socket event would otherwise leave pending
    // bubbles stuck on Queued/Started forever.
    useRunStatusPolling(messages, setMessages, chatId);

    // Show error toast when there's an error loading messages
    useEffect(() => {
        if (messagesError && chatId) {
            toast.error('Failed to load messages', {
                description: messagesError.message || 'An error occurred while fetching messages. Please try again.',
                duration: 5000,
            });
        }
    }, [messagesError, chatId]);

    const previousChatIdRef = useRef<string | null>(chatId);

    // Clear message state before merge/hydration when switching conversations.
    useLayoutEffect(() => {
        if (!chatId) {
            previousChatIdRef.current = chatId;
            return;
        }

        if (chatId === previousChatIdRef.current) {
            return;
        }

        const isNewConversationTransition = chatId === newlyCreatedConversationIdRef.current;
        if (!isNewConversationTransition) {
            setMessages([]);
            setIsTransitioningToNewConversation(false);
        }

        previousChatIdRef.current = chatId;
    }, [chatId]);

    const conversationItemsForChat = useMemo(
        () => (chatId ? filterMessagesForConversation(conversationItems, chatId) : []),
        [chatId, conversationItems]
    );

    // Transform conversationItems to MessageType and merge with socket messages
    useEffect(() => {
        if (!chatId) {
            if (!isCreatingConversationRef.current) {
                setMessages([]);
            }
            return;
        }

        if (isCreatingConversationRef.current) {
            return;
        }

        if (hasStaleConversationItems(conversationItems, chatId)) {
            return;
        }

        // During transition to new conversation, preserve existing messages
        // Only merge when we have actual API data
        if (isTransitioningToNewConversation) {
            // If we have conversationItems, merge them; otherwise preserve existing messages
            if (conversationItemsForChat.length > 0) {
                setMessages((prev) => mergeConversationItemsIntoMessages(prev, conversationItemsForChat, true));
            }
            // If conversationItems is empty, keep existing messages (don't clear)
            return;
        }

        // Normal merge for existing conversations
        setMessages((prev) => mergeConversationItemsIntoMessages(prev, conversationItemsForChat, false));
    }, [chatId, conversationItems, conversationItemsForChat, isTransitioningToNewConversation]);

    // Hydrate open Agent Runs after persisted messages are merged (reload / chat switch).
    usePendingRunHydration({
        chatId,
        conversationItems,
        initialLoading,
        setMessages,
    });

    // Finish new-conversation transition bookkeeping
    useEffect(() => {
        if (chatId && chatId === newlyCreatedConversationIdRef.current) {
            const timeoutId = setTimeout(() => {
                newlyCreatedConversationIdRef.current = null;
                setIsTransitioningToNewConversation(false);
            }, 1000);

            return () => clearTimeout(timeoutId);
        }
    }, [chatId]);

    const { scrollContainerRef, scrollToBottomAfterPaint } = useChatScrollToBottom({
        chatId,
        initialLoading,
        messages,
    });

    const handleFeedback = useCallback(
        async (
            feedbackType: 'Thumbs Up' | 'Thumbs Down',
            options?: { agentMessageId?: string; comments?: string }
        ) => {
            if (!agentName) {
                toast.error('Select an agent before submitting feedback');
                return;
            }

            try {
                await createAgentRunFeedback({
                    agent: agentName,
                    feedback: feedbackType,
                    comments: options?.comments,
                    conversation: chatId ?? undefined,
                    agent_message: options?.agentMessageId,
                });
                toast.success('Thanks for the feedback!');
            } catch (error) {
                console.error(error);
            }
        },
        [agentName, chatId]
    );

    if (isNewChat && !agentName) {
        return (
            <EmptyChatState />
        );
    }

    // Don't show loading state if we already have messages (e.g., during transition)
    const shouldShowLoading = initialLoading && messages.length === 0;

    return (
        <div className="flex-1 flex flex-col overflow-hidden min-h-0">
            <div className="flex-1 overflow-y-auto min-h-0" ref={scrollContainerRef}>
                <div className="max-w-4xl mx-auto px-6 py-4 space-y-4">
                    {shouldShowLoading ? (
                        <div className="flex items-center justify-center py-20">
                            <p className="text-sm text-muted-foreground">Loading messages...</p>
                        </div>
                    ) : messagesError && !initialLoading ? (
                        <div className="flex items-center justify-center py-20">
                            <div className="text-center">
                                <p className="text-sm text-destructive mb-2">Failed to load messages</p>
                                <p className="text-xs text-muted-foreground">{messagesError.message || 'An error occurred while fetching messages.'}</p>
                            </div>
                        </div>
                    ) : messages.length === 0 && !isNewChat ? (
                        <div className="flex items-center justify-center py-20">
                            <p className="text-sm text-muted-foreground">No messages yet</p>
                        </div>
                    ) : (
                        <div className="mt-2 space-y-8">
                            {(hasMore && !isNewChat && !newlyCreatedConversationIdRef.current && !isCreatingConversationRef.current) && (
                                <div ref={sentinelRef} className="h-2 w-full opacity-0" aria-hidden="true" />
                            )}
                            {loadingMore && (
                                <div className="text-xs text-muted-foreground text-center py-2">
                                    Loading previous messages...
                                </div>
                            )}
                            {messages.map((message) => (
                                <ChatMessageComponent 
                                    key={message.key} 
                                    message={message} 
                                    agentName={agentName}
                                    agentColor={agentColor}
                                    showToolExecutionDetails={showToolExecutionDetails}
                                    status={status}
                                    loadingType={loadingType}
                                    onFeedback={handleFeedback}
                                    scrollToBottomAfterPaint={scrollToBottomAfterPaint}
                                />
                            ))}
                        </div>
                    )}
                </div>
            </div>
            <div className="max-w-4xl mx-auto w-full shrink-0">
            <ChatInput 
                chatId={chatId} 
                agentName={agentName}
                onConversationCreated={onConversationCreated}
                getNewConversationPath={getNewConversationPath}
                onStatusChange={setStatus}
                onLoadingTypeChange={setLoadingType}
                isCreatingConversationRef={isCreatingConversationRef}
                newlyCreatedConversationIdRef={newlyCreatedConversationIdRef}
                setMessages={setMessages}
                isModelMismatch={isModelMismatch}
                scrollToBottomAfterPaint={scrollToBottomAfterPaint}
                allowFileUpload={allowFileUpload}
                maxUploadSizeMb={maxUploadSizeMb}
                runImmediately={runImmediately}
            />
            </div>
        </div>
    );
}
