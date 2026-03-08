import { useEffect, useState, useCallback, useRef, useMemo } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { getConversationMessages, createAgentRunFeedback, getConversation, type ChatMessage } from "@/services/chatApi";
import { getAgent } from "@/services/agentApi";
import { useInfiniteScroll } from "@/hooks/useInfiniteScroll";
import { useChatSocket, type ToolCallEvent, type NewAgentMessageEvent } from '@/hooks/useChatSocket';
import { ChatMessage as ChatMessageComponent } from './ChatMessage';
import { ChatInput } from './ChatInput';
import { EmptyChatState } from './EmptyChatState';
import type { MessageType } from './types';
import type { LoadingType } from './ChatInput';
import { useChatAgentIdentity } from './useChatAgentIdentity';
import { useChatScrollToBottom } from './useChatScrollToBottom';
import {
    mergeConversationItemsIntoMessages,
    upsertAgentMessageFromSocket,
    upsertToolUpdateFromSocket,
} from './chatMessageList.mappers';

interface ChatMessageListProps {
    chatId?: string | null;
    onConversationCreated?: (conversationId: string, agentName?: string) => void;
}

export function ChatMessageList({ 
    chatId: chatIdProp, 
    onConversationCreated 
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

    const { agentName, agentColor } = useChatAgentIdentity(chatId, searchParams);

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

    useChatSocket({
        conversationId: chatId,
        onToolUpdate: handleToolUpdate,
        onNewMessage: handleNewMessage,
    });

    // Show error toast when there's an error loading messages
    useEffect(() => {
        if (messagesError && chatId) {
            toast.error('Failed to load messages', {
                description: messagesError.message || 'An error occurred while fetching messages. Please try again.',
                duration: 5000,
            });
        }
    }, [messagesError, chatId]);

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

        // During transition to new conversation, preserve existing messages
        // Only merge when we have actual API data
        if (isTransitioningToNewConversation) {
            // If we have conversationItems, merge them; otherwise preserve existing messages
            if (conversationItems.length > 0) {
                setMessages((prev) => mergeConversationItemsIntoMessages(prev, conversationItems, true));
            }
            // If conversationItems is empty, keep existing messages (don't clear)
            return;
        }

        // Normal merge for existing conversations
        setMessages((prev) => mergeConversationItemsIntoMessages(prev, conversationItems, false));
    }, [chatId, conversationItems, isTransitioningToNewConversation]);

    // Reset state when switching chats
    const previousChatIdRef = useRef<string | null>(chatId);
    useEffect(() => {
        if (chatId && chatId !== previousChatIdRef.current) {
            const isNewConversationTransition = chatId === newlyCreatedConversationIdRef.current;
            
            if (!isNewConversationTransition) {
                // Clear messages when switching to a different conversation
                setMessages([]);
                // Ensure transition state is cleared for non-transition cases
                setIsTransitioningToNewConversation(false);
            }
            
            // Delay clearing the ref until after messages are safely loaded
            // This prevents race conditions with the merge effect
            if (isNewConversationTransition) {
                // Clear ref after transition period and message loading
                // Also clear transition state to ensure fetching is enabled
                const timeoutId = setTimeout(() => {
                    newlyCreatedConversationIdRef.current = null;
                    setIsTransitioningToNewConversation(false);
                }, 1000); // Longer delay to ensure messages are loaded
                
                return () => clearTimeout(timeoutId);
            }
        }
        previousChatIdRef.current = chatId;
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
                onStatusChange={setStatus}
                onLoadingTypeChange={setLoadingType}
                isCreatingConversationRef={isCreatingConversationRef}
                newlyCreatedConversationIdRef={newlyCreatedConversationIdRef}
                setMessages={setMessages}
                isModelMismatch={isModelMismatch}
                scrollToBottomAfterPaint={scrollToBottomAfterPaint}
            />
            </div>
        </div>
    );
}
