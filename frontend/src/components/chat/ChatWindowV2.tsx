import { useEffect, useState, useCallback, useRef, useMemo } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import type { ToolUIPart } from 'ai';
import { useSidebar } from "../ui/sidebar";
import ChatAvatar from "./ChatAvatar";
import { getInitials } from "@/utils/getInitials";
import { useUser } from "@/contexts/UserContext";
import { getConversation, getConversationMessages, newConversation, sendMessageToConversation, createAgentRunFeedback, type ChatMessage } from "@/services/chatApi";
import { getAgent } from "@/services/agentApi";
import type { AgentDoc } from "@/types/agent.types";
import { useInfiniteScroll } from "@/hooks/useInfiniteScroll";
import { toDate } from "@/utils/time";
import { cn } from "@/lib/utils";
import { Button } from "../ui/button";
import { CornerDownLeft } from "lucide-react";
import { Textarea } from "../ui/textarea";
import { Message, MessageContent, MessageResponse } from '@/components/ai-elements/message';
import { Tool, ToolHeader, ToolContent, ToolInput, ToolOutput } from '@/components/ai-elements/tool';
import type { ExtendedToolState } from '@/components/ai-elements/types';
import { useChatSocket, type ToolCallEvent, type NewAgentMessageEvent } from '@/hooks/useChatSocket';
import { CopyButton } from './CopyButton';
import { MessageActions } from './MessageActions';
import { MessageLoadingState } from './MessageLoadingState';
import { Image } from '@/components/ai-elements/image';
import { Skeleton } from '@/components/ui/skeleton';
import { ShortcutKey } from "../ui/shortcut-key";
import { DEFAULT_AGENT_COLOR } from "@/data/color";

function formatTime(timestamp?: string): string {
    if (!timestamp) return '';
    const date = toDate(timestamp);
    if (!date) return '';
    const hours = date.getHours().toString().padStart(2, '0');
    const minutes = date.getMinutes().toString().padStart(2, '0');
    return `${hours}:${minutes}`;
}

// Map tool_status to ExtendedToolState
const mapToolStatusToState = (status?: string): ExtendedToolState => {
  switch (status) {
    case 'Started':
      return 'input-available';
    case 'Queued':
      return 'input-streaming';
    case 'Completed':
      return 'output-available';
    case 'Failed':
      return 'output-error';
    default:
      return 'input-streaming';
  }
};

type MessageType = {
  key: string;
  from: 'user' | 'assistant';
  versions: {
    id: string;
    content: string;
  }[];
  kind?: string;
  generatedImage?: string;
  tools?: {
    tool_call_id: string;
    name: string;
    description: string;
    status: ToolUIPart['state'];
    parameters: Record<string, unknown>;
    result: string | undefined;
    error: string | undefined;
  }[];
};

interface ChatWindowProps {
    chatId?: string | null;
    onConversationCreated?: (conversationId: string) => void;
}

export default function ChatWindow({ chatId: chatIdProp, onConversationCreated }: ChatWindowProps){
    const {setOpen} = useSidebar();
    
    // Close sidebar on initial mount only
    useEffect(() => {
        setOpen(false);
    }, []);
    
    return (
        <div className="w-full h-full flex flex-col overflow-hidden bg-background">
           <ChatWindowHeader chatId={chatIdProp} />
           <ChatMessageList chatId={chatIdProp} onConversationCreated={onConversationCreated} />
        </div>
    )
}

function ChatWindowHeader({ chatId: chatIdProp }: { chatId?: string | null }){
    const { chatId: routeChatId } = useParams<{ chatId?: string }>();
    const [searchParams] = useSearchParams();
    const chatId = chatIdProp ?? (routeChatId && routeChatId !== 'new' ? routeChatId : null);
    
    const [agent, setAgent] = useState<AgentDoc | null>(null);

    useEffect(() => {
        let cancelled = false;

        async function fetchAgentData() {
            try {
                let agentName: string | null = null;

                // Get agent name from conversation or query params
                if (chatId) {
                    // Existing conversation - get agent from conversation
                    try {
                        const conversation = await getConversation(chatId);
                        if (conversation?.agent) {
                            agentName = conversation.agent;
                        }
                    } catch (error) {
                        console.error('Error fetching conversation:', error);
                        if (!cancelled) {
                            toast.error("Failed to load conversation", {
                                description: "Could not fetch conversation details. Please try again.",
                                duration: 5000,
                            });
                        }
                        return;
                    }
                } else {
                    // New chat - get agent from query params
                    agentName = searchParams.get('agent');
                }

                // Fetch agent details if we have an agent name
                if (agentName) {
                    try {
                        const agentData = await getAgent(agentName);
                        if (!cancelled) {
                            setAgent(agentData);
                        }
                    } catch (error) {
                        console.error('Error fetching agent:', error);
                        if (!cancelled) {
                            toast.error("Failed to load agent", {
                                description: "Could not fetch agent details. Please try again.",
                                duration: 5000,
                            });
                            setAgent(null);
                        }
                    }
                } else {
                    if (!cancelled) {
                        setAgent(null);
                    }
                }
            } catch (error) {
                console.error('Error fetching agent data:', error);
                if (!cancelled) {
                    toast.error("Failed to load agent data", {
                        description: "An unexpected error occurred. Please try again.",
                        duration: 5000,
                    });
                    setAgent(null);
                }
            }
        }

        fetchAgentData();

        return () => {
            cancelled = true;
        };
    }, [chatId, searchParams]);

    if (!agent) {
        return (
            <header className="h-16 px-6 border-b border-zinc-200 flex items-center justify-between bg-white/80 backdrop-blur-md sticky top-0 z-10">
                <div className="flex gap-x-4 items-center">
                    <ChatAvatar variant="chat_ai">?</ChatAvatar>
                    <div className="flex flex-col">
                        <span className="font-semibold text-sm text-zinc-900">No agent selected</span>
                        <span className="text-xs text-zinc-500">Select an agent to start chatting</span>
                    </div>
                </div>
            </header>
        );
    }

    return (
        <header className="h-16 px-6 border-b border-zinc-200 flex items-center justify-between bg-white/80 backdrop-blur-md sticky top-0 z-10">
            <div className="flex gap-x-4 items-center">
                <ChatAvatar variant="chat_ai" color={agent.agent_color || DEFAULT_AGENT_COLOR}>
                    {getInitials(agent.agent_name)}
                </ChatAvatar>
                <div className="flex flex-col">
                    <div className="flex gap-x-2 items-center">
                        <span className="font-semibold text-sm text-zinc-900">{agent.agent_name}</span>
                        {agent.model && (
                            <span className="px-1.5 py-0.5 rounded bg-indigo-500/10 border border-indigo-500/20 text-[10px] font-medium text-indigo-400">
                                {agent.model}
                            </span>
                        )}
                    </div>
                    {agent.description && (
                        <span className="text-xs text-zinc-500 max-w-[200px] truncate">
                            {agent.description}
                        </span>
                    )}
                </div>
            </div>
        </header>
    )
}

function ChatMessageList({ 
    chatId: chatIdProp, 
    onConversationCreated 
}: { 
    chatId?: string | null;
    onConversationCreated?: (conversationId: string) => void;
}) {
    const { chatId: routeChatId } = useParams<{ chatId?: string }>();
    const [searchParams] = useSearchParams();
    const chatId = chatIdProp ?? (routeChatId && routeChatId !== 'new' ? routeChatId : null);
    const isNewChat = !chatId;
    
    const [agentName, setAgentName] = useState<string>('');
    const [agentColor, setAgentColor] = useState<string | null>(null);
    const [messages, setMessages] = useState<MessageType[]>([]);
    const [status, setStatus] = useState<'submitted' | 'streaming' | 'ready' | 'error'>('ready');
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const isCreatingConversationRef = useRef(false);
    const newlyCreatedConversationIdRef = useRef<string | null>(null);

    // Get agent name and color from conversation or query params
    useEffect(() => {
        if (chatId) {
            getConversation(chatId)
                .then(async (conversation) => {
                    if (conversation?.agent) {
                        setAgentName(conversation.agent);
                        // Fetch agent to get color
                        try {
                            const agentData = await getAgent(conversation.agent);
                            setAgentColor(agentData.agent_color || null);
                        } catch (error) {
                            console.error('Failed to load agent color', error);
                            setAgentColor(null);
                        }
                    }
                })
                .catch((error) => {
                    console.error('Failed to load conversation agent', error);
                });
        } else {
            const agentFromQuery = searchParams.get('agent') ?? '';
            setAgentName(agentFromQuery);
            // Fetch agent to get color
            if (agentFromQuery) {
                getAgent(agentFromQuery)
                    .then((agentData) => {
                        setAgentColor(agentData.agent_color || null);
                    })
                    .catch((error) => {
                        console.error('Failed to load agent color', error);
                        setAgentColor(null);
                    });
            } else {
                setAgentColor(null);
            }
        }
    }, [chatId, searchParams]);

    // Memoize initialParams to ensure stable reference but detect chatId changes
    const initialParams = useMemo(() => {
        return chatId ? { conversation: chatId } : {};
    }, [chatId]);

    // Don't fetch messages if we're transitioning to a newly created conversation
    // Use useMemo to make it reactive - it will recalculate when chatId changes
    const shouldFetchMessages = useMemo(() => {
        return Boolean(chatId) && chatId !== newlyCreatedConversationIdRef.current;
    }, [chatId]);

    // Fetch messages
    const {
        items: conversationItems,
        initialLoading,
        loadingMore,
        hasMore,
        sentinelRef,
    } = useInfiniteScroll({
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
        if (event.conversation_id !== chatId) {
            return;
        }

        setMessages((prev) => {
            let parsedArgs: Record<string, unknown> = {};
            if (event.tool_args) {
                try {
                    parsedArgs = typeof event.tool_args === 'string' 
                        ? JSON.parse(event.tool_args) 
                        : (event.tool_args as Record<string, unknown>);
                } catch {
                    parsedArgs = {};
                }
            }

            let parsedResult: string | undefined = undefined;
            if (event.tool_result) {
                try {
                    parsedResult = typeof event.tool_result === 'string'
                        ? event.tool_result
                        : JSON.stringify(event.tool_result, null, 2);
                } catch {
                    parsedResult = String(event.tool_result);
                }
            }

            const updatedTool = {
                tool_call_id: event.tool_call_id,
                name: event.tool_name,
                description: event.tool_name,
                status: mapToolStatusToState(event.tool_status) as any,
                parameters: parsedArgs,
                result: event.tool_status === 'Completed' ? parsedResult : undefined,
                error: event.tool_status === 'Failed' ? (event.error || parsedResult) : undefined,
            };

            const messageIndex = prev.findIndex((msg) => msg.key === event.agent_run_id);

            if (messageIndex >= 0) {
                const message = prev[messageIndex];
                const existingTools = message.tools || [];
                const toolIndex = existingTools.findIndex(
                    (tool) => tool.name === event.tool_name
                );

                const updatedTools = [...existingTools];
                if (toolIndex >= 0) {
                    updatedTools[toolIndex] = updatedTool;
                } else {
                    updatedTools.push(updatedTool);
                }

                const isImageGeneration = event.tool_name === 'generate_image' && event.type === 'tool_call_started';
                
                const updated = [...prev];
                updated[messageIndex] = {
                    ...message,
                    kind: isImageGeneration ? 'Image' : message.kind,
                    tools: updatedTools,
                };
                return updated;
            } else {
                const isImageGeneration = event.tool_name === 'generate_image' && event.type === 'tool_call_started';
                
                const newMessage: MessageType = {
                    key: event.agent_run_id,
                    from: 'assistant',
                    kind: isImageGeneration ? 'Image' : undefined,
                    versions: [
                        {
                            id: event.message_id || event.agent_run_id,
                            content: '',
                        },
                    ],
                    tools: [updatedTool],
                };
                return [...prev, newMessage];
            }
        });
    }, [chatId]);

    // Handle new agent message events (e.g., Image messages)
    const handleNewMessage = useCallback((event: NewAgentMessageEvent) => {
        if (event.conversation_id !== chatId) {
            return;
        }

        setMessages((prev) => {
            const messageIndex = prev.findIndex((msg) => 
                msg.versions.some((v) => v.id === event.message_id)
            );

            if (messageIndex >= 0) {
                const updated = [...prev];
                updated[messageIndex] = {
                    ...updated[messageIndex],
                    kind: event.kind,
                    generatedImage: event.generated_image,
                    versions: updated[messageIndex].versions.map((v) => 
                        v.id === event.message_id 
                            ? { ...v, content: event.content || v.content }
                            : v
                    ),
                };
                return updated;
            } else {
                const newMessage: MessageType = {
                    key: event.message_id,
                    from: 'assistant',
                    kind: event.kind,
                    generatedImage: event.generated_image,
                    versions: [
                        {
                            id: event.message_id,
                            content: event.content || '',
                        },
                    ],
                };
                return [...prev, newMessage];
            }
        });
    }, [chatId]);

    useChatSocket({
        conversationId: chatId,
        onToolUpdate: handleToolUpdate,
        onNewMessage: handleNewMessage,
    });

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

        if (chatId === newlyCreatedConversationIdRef.current) {
            // For newly created conversations, don't overwrite messages from API
            // They're already in state from the immediate display
            return;
        }

        setMessages((prev) => {
            const mapped: MessageType[] = conversationItems.map((item) => {
                const tempMessage = prev.find((msg) => msg.key === item.id);
                const tempTools = tempMessage?.tools || [];

                const baseMessage: MessageType = {
                    key: item.id,
                    from: item.isAgent ? 'assistant' : 'user',
                    kind: item.kind,
                    generatedImage: item.generatedImage,
                    versions: [
                        {
                            id: item.id,
                            content: item.content,
                        },
                    ],
                };

                if (item.kind === 'Tool Result' && item.toolName) {
                    let parsedArgs: Record<string, unknown> = {};
                    if (item.toolArgs) {
                        try {
                            parsedArgs = typeof item.toolArgs === 'string' 
                                ? JSON.parse(item.toolArgs) 
                                : (item.toolArgs as Record<string, unknown>);
                        } catch {
                            parsedArgs = {};
                        }
                    }

                    const tempTool = tempTools.find((tool) => tool.name === item.toolName);
                    const tool_call_id = tempTool?.tool_call_id || `temp-${item.id}-${item.toolName}`;

                    const apiTool = {
                        tool_call_id,
                        name: item.toolName,
                        description: item.toolName,
                        status: mapToolStatusToState(item.toolStatus) as any,
                        parameters: parsedArgs,
                        result: item.toolStatus === 'Completed' ? item.content : undefined,
                        error: item.toolStatus === 'Failed' ? item.content : undefined,
                    };

                    const toolMap = new Map<string, typeof apiTool>();
                    tempTools.forEach((tool) => {
                        toolMap.set(tool.tool_call_id, tool as any);
                    });
                    
                    if (!toolMap.has(tool_call_id)) {
                        toolMap.set(tool_call_id, apiTool);
                    }
                    
                    baseMessage.tools = Array.from(toolMap.values());
                } else if (tempTools.length > 0) {
                    baseMessage.tools = tempTools;
                }

                return baseMessage;
            });

            const apiMessageIds = new Set(conversationItems.map((item) => item.id));
            const remainingTempMessages = prev.filter(
                (msg) => !apiMessageIds.has(msg.key) && msg.tools && msg.tools.length > 0
            );

            return [...mapped, ...remainingTempMessages];
        });
    }, [chatId, conversationItems]);

    // Reset state when switching chats
    const previousChatIdRef = useRef<string | null>(chatId);
    useEffect(() => {
        if (chatId && chatId !== previousChatIdRef.current) {
            const isTransitioningToNewConversation = chatId === newlyCreatedConversationIdRef.current;
            
            if (!isTransitioningToNewConversation) {
                setMessages([]);
            }
            
            if (isTransitioningToNewConversation) {
                newlyCreatedConversationIdRef.current = null;
            }
        }
        previousChatIdRef.current = chatId;
    }, [chatId]);

    // Scroll to bottom when messages change
    useEffect(() => {
        if (messagesEndRef.current) {
            // Use requestAnimationFrame to ensure DOM is updated
            requestAnimationFrame(() => {
                messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
            });
        }
    }, [messages.length, messages]);

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
            <div className="flex-1 flex items-center justify-center">
                <div className="text-center space-y-2">
                    <p className="text-sm text-muted-foreground">Select an agent to start chatting</p>
                </div>
            </div>
        );
    }

    return (
        <div className="flex-1 flex flex-col overflow-hidden">
            <div className="flex-1 overflow-y-auto">
                <div className="max-w-4xl mx-auto px-6 py-4 space-y-4">
                    {initialLoading ? (
                        <div className="flex items-center justify-center h-full">
                            <p className="text-sm text-muted-foreground">Loading messages...</p>
                        </div>
                    ) : messages.length === 0 && !isNewChat ? (
                        <div className="flex items-center justify-center h-full">
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
                                <ChatMessage 
                                    key={message.key} 
                                    message={message} 
                                    agentName={agentName}
                                    agentColor={agentColor}
                                    status={status}
                                    onFeedback={handleFeedback}
                                />
                            ))}
                            <div ref={messagesEndRef} />
                        </div>
                    )}
                </div>
            </div>
            <div className="max-w-4xl mx-auto w-full">
            <ChatInput 
                chatId={chatId} 
                agentName={agentName}
                onConversationCreated={onConversationCreated}
                onStatusChange={setStatus}
                isCreatingConversationRef={isCreatingConversationRef}
                newlyCreatedConversationIdRef={newlyCreatedConversationIdRef}
                setMessages={setMessages}
            />
            </div>
        </div>
    );
}

function ChatMessage({ 
    message, 
    agentName,
    agentColor,
    status,
    onFeedback,
}: { 
    message: MessageType;
    agentName: string;
    agentColor: string | null;
    status: 'submitted' | 'streaming' | 'ready' | 'error';
    onFeedback: (feedback: 'Thumbs Up' | 'Thumbs Down', options?: { agentMessageId?: string; comments?: string }) => void;
}) {
    const { user } = useUser();
    const isUser = message.from === 'user';
    const timestamp = message.versions[0]?.id ? undefined : undefined; // We'll get timestamp from message if available
    const timeDisplay = timestamp ? formatTime(timestamp) : '';
    const userInitials = user?.full_name ? getInitials(user.full_name) : 'You';

    return (
        <div className={cn("flex gap-3 group relative", isUser ? "flex-row" : "flex-row")}>
            <ChatAvatar 
                variant={isUser ? "chat_user" : "chat_ai"}
                color={!isUser ? (agentColor || DEFAULT_AGENT_COLOR) : undefined}
            >
                {isUser ? userInitials : getInitials(agentName)}
            </ChatAvatar>
            <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm font-medium text-zinc-900">
                        {isUser ? "You" : agentName}
                    </span>
                    {timeDisplay && (
                        <span className="text-xs text-zinc-400">
                            {timeDisplay}
                        </span>
                    )}
                </div>
                
                {message.tools && message.tools.length > 0 ? (
                    message.tools.map((tool, toolIndex) => (
                        <Tool key={`${message.key}-tool-${toolIndex}`}>
                            <ToolHeader
                                title={tool.name}
                                type={`tool-${tool.name}` as any}
                                state={tool.status}
                            />
                            <ToolContent>
                                <ToolInput input={tool.parameters} />
                                <ToolOutput
                                    output={tool.result}
                                    errorText={tool.error}
                                />
                            </ToolContent>
                        </Tool>
                    ))
                ) : (
                    <Message from={message.from} className={cn(isUser && "!ml-0")}>
                        <MessageContent className={cn(isUser && "!ml-0")}>
                            {/* Show loading state while message is generating */}
                            {(status === 'submitted' || status === 'streaming') && 
                             message.from === 'assistant' && 
                             (!message.versions[0]?.content || message.versions[0].content.trim() === '') && (
                                <MessageLoadingState
                                    hasTools={!!message.tools && message.tools.length > 0}
                                    toolName={message.tools?.[0]?.name}
                                />
                            )}
                            {message.kind === 'Image' ? (
                                <div className="flex flex-col gap-2">
                                    {message.generatedImage ? (
                                        <Image 
                                            src={message.generatedImage} 
                                            alt={message.versions[0]?.content || 'Generated image'}
                                            className="max-w-full h-auto rounded-lg border max-h-[512px] object-contain"
                                            showDownloadButton={true}
                                        />
                                    ) : (
                                        <Skeleton className="w-full h-[512px] rounded-lg" />
                                    )}
                                    {message.versions[0]?.content && (
                                        <MessageResponse>{message.versions[0].content}</MessageResponse>
                                    )}
                                </div>
                            ) : !((status === 'submitted' || status === 'streaming') && 
                                  message.from === 'assistant' && 
                                  (!message.versions[0]?.content || message.versions[0].content.trim() === '') && 
                                  !message.tools) && (
                                <MessageResponse>{message.versions[0]?.content || ''}</MessageResponse>
                            )}
                        </MessageContent>
                        {/* Actions for assistant messages */}
                        {message.from === 'assistant' && message.versions[0]?.content && !message.tools && (
                            <div className="opacity-0 transition-opacity group-hover:opacity-100">
                                <MessageActions
                                    content={message.versions[0].content}
                                    onFeedback={onFeedback}
                                    agentMessageId={message.versions[0].id}
                                />
                            </div>
                        )}
                        {/* Actions for user messages */}
                        {message.from === 'user' && message.versions[0]?.content && (
                            <div className="opacity-0 transition-opacity group-hover:opacity-100 flex items-center gap-2 text-muted-foreground">
                                <CopyButton content={message.versions[0].content} />
                            </div>
                        )}
                    </Message>
                )}
            </div>
        </div>
    );
}

function ChatInput({ 
    chatId, 
    agentName,
    onConversationCreated,
    onStatusChange,
    isCreatingConversationRef,
    newlyCreatedConversationIdRef,
    setMessages,
}: { 
    chatId: string | null;
    agentName: string;
    onConversationCreated?: (conversationId: string) => void;
    onStatusChange: (status: 'submitted' | 'streaming' | 'ready' | 'error') => void;
    isCreatingConversationRef: React.MutableRefObject<boolean>;
    newlyCreatedConversationIdRef: React.MutableRefObject<string | null>;
    setMessages: React.Dispatch<React.SetStateAction<MessageType[]>>;
}) {
    const [message, setMessage] = useState('');
    const [isSubmitting, setIsSubmitting] = useState(false);
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    
    const MIN_HEIGHT = 60;
    const MAX_HEIGHT = 200;

    // Auto-focus input field when chat window opens or chatId changes
    useEffect(() => {
        // Small delay to ensure DOM is ready
        const timer = setTimeout(() => {
            if (textareaRef.current) {
                textareaRef.current.focus();
            }
        }, 100);

        return () => clearTimeout(timer);
    }, [chatId]);

    const handleSubmit = useCallback(async (e: React.FormEvent) => {
        e.preventDefault();
        
        if (!message.trim() || !agentName || isSubmitting) {
            return;
        }

        const messageText = message.trim();
        setIsSubmitting(true);
        onStatusChange('submitted');

        // Add user message immediately
        const userMessageKey = `user-${Date.now()}`;
        const userMessage: MessageType = {
            key: userMessageKey,
            from: 'user',
            versions: [
                {
                    id: userMessageKey,
                    content: messageText,
                },
            ],
        };
        setMessages((prev) => [...prev, userMessage]);

        // Clear input immediately
        setMessage('');
        if (textareaRef.current) {
            textareaRef.current.focus();
        }

        try {
            if (!chatId) {
                // New conversation
                isCreatingConversationRef.current = true;
                
                // Add placeholder assistant message
                const assistantMessageId = `assistant-${Date.now()}`;
                const assistantMessage: MessageType = {
                    key: assistantMessageId,
                    from: 'assistant',
                    versions: [
                        {
                            id: assistantMessageId,
                            content: '',
                        },
                    ],
                };
                setMessages((prev) => [...prev, assistantMessage]);

                const response = await newConversation({
                    agent: agentName,
                    message: messageText,
                });

                const conversationId = response.message?.conversation_id;
                const responseText = response.message?.run?.response;

                if (responseText) {
                    onStatusChange('streaming');
                    // Update assistant message with response
                    setMessages((prev) =>
                        prev.map((msg) =>
                            msg.key === assistantMessageId
                                ? {
                                      ...msg,
                                      versions: [
                                          {
                                              id: assistantMessageId,
                                              content: responseText,
                                          },
                                      ],
                                  }
                                : msg
                        )
                    );
                    onStatusChange('ready');
                } else {
                    onStatusChange('ready');
                }

                if (conversationId && onConversationCreated) {
                    newlyCreatedConversationIdRef.current = conversationId;
                    setTimeout(() => {
                        isCreatingConversationRef.current = false;
                    }, 100);
                    onConversationCreated(conversationId);
                } else {
                    isCreatingConversationRef.current = false;
                }

                // Focus input after successful message creation
                setTimeout(() => {
                    if (textareaRef.current) {
                        textareaRef.current.focus();
                    }
                }, 200);
            } else {
                // Existing conversation
                // Add placeholder assistant message
                const assistantMessageId = `assistant-${Date.now()}`;
                const assistantMessage: MessageType = {
                    key: assistantMessageId,
                    from: 'assistant',
                    versions: [
                        {
                            id: assistantMessageId,
                            content: '',
                        },
                    ],
                };
                setMessages((prev) => [...prev, assistantMessage]);

                const response = await sendMessageToConversation({
                    conversation: chatId,
                    message: messageText,
                });

                // Update assistant message with response
                if (response.message?.response) {
                    onStatusChange('streaming');
                    setMessages((prev) =>
                        prev.map((msg) =>
                            msg.key === assistantMessageId
                                ? {
                                      ...msg,
                                      versions: [
                                          {
                                              id: assistantMessageId,
                                              content: response.message.response,
                                          },
                                      ],
                                  }
                                : msg
                        )
                    );
                }
                onStatusChange('ready');

                // Focus input after successful message send
                setTimeout(() => {
                    if (textareaRef.current) {
                        textareaRef.current.focus();
                    }
                }, 100);
            }
        } catch (error) {
            console.error('Error sending message:', error);
            onStatusChange('error');
            toast.error('Failed to send message', {
                description: error instanceof Error ? error.message : 'An error occurred',
            });
        } finally {
            setIsSubmitting(false);
        }
    }, [message, agentName, chatId, onConversationCreated, isSubmitting, onStatusChange, isCreatingConversationRef, newlyCreatedConversationIdRef, setMessages]);

    const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSubmit(e as any);
        }
    }, [handleSubmit]);

    // Auto-resize textarea based on content
    const adjustTextareaHeight = useCallback(() => {
        const textarea = textareaRef.current;
        if (!textarea) return;

        // Use double requestAnimationFrame to ensure DOM has fully updated
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                if (!textarea) return;
                
                // Store current min-height to restore later
                const currentMinHeight = textarea.style.minHeight;
                
                // Reset height to get accurate scrollHeight measurement
                // Use a very small value instead of 0 to avoid layout issues
                textarea.style.height = '1px';
                textarea.style.minHeight = '0';
                textarea.style.overflowY = 'hidden';
                
                // Force a reflow to ensure accurate measurement
                void textarea.offsetHeight;
                
                // Get the scrollHeight (this is the natural height of the content including padding)
                const scrollHeight = textarea.scrollHeight;
                
                // Restore min-height
                textarea.style.minHeight = currentMinHeight || '';
                
                // Calculate new height, ensuring it's within bounds
                const newHeight = Math.min(Math.max(scrollHeight, MIN_HEIGHT), MAX_HEIGHT);
                
                // Always apply the calculated height to ensure accuracy
                textarea.style.height = `${newHeight}px`;
                
                // Enable scrolling if content exceeds max height
                if (scrollHeight > MAX_HEIGHT) {
                    textarea.style.overflowY = 'auto';
                } else {
                    textarea.style.overflowY = 'hidden';
                }
            });
        });
    }, []);

    // Adjust height when message changes
    useEffect(() => {
        if (!textareaRef.current) return;
        
        // If message is empty, reset to min height immediately
        if (!message) {
            const textarea = textareaRef.current;
            textarea.style.height = `${MIN_HEIGHT}px`;
            textarea.style.overflowY = 'hidden';
            return;
        }
        
        // Otherwise, adjust height based on content
        adjustTextareaHeight();
    }, [message, adjustTextareaHeight]);

    if (!agentName) {
        return null;
    }

    return (
        <div className="px-6 pb-6 pt-2">
            <form onSubmit={handleSubmit} className="flex gap-2 items-end">
                <div className="w-full border border-zinc-200 rounded-xl shadow-2xl focus-within:ring-1 focus-within:ring-ring transition-all">
                    <Textarea
                        ref={textareaRef}
                        value={message}
                        onChange={(e) => {
                            setMessage(e.target.value);
                            // Height adjustment is handled in useEffect
                        }}
                        rows={2}
                        onKeyDown={handleKeyDown}
                        placeholder="Type your message..."
                        className="p-4 w-full min-h-[60px] max-h-[200px] resize-none focus-visible:ring-0 border-none shadow-none"
                        style={{ 
                            height: `${MIN_HEIGHT}px`
                        }}
                        disabled={isSubmitting}
                    />
                    <div className="px-3 pb-3 w-full flex items-center justify-end gap-x-2 mt-2">
                        <span className="flex items-center gap-x-1 text-[10px] text-zinc-400">
                            Use
                            <ShortcutKey>
                                Shift + Enter
                            </ShortcutKey>
                            for new line
                        </span>
                        <Button
                            type="submit"
                            disabled={!message.trim() || isSubmitting}
                            size="icon"
                            className="shrink-0"
                        >
                            <CornerDownLeft/>
                        </Button>
                    </div>
                </div>
            </form>
            <p className="mt-3 text-[10px] text-zinc-400 text-center">AI output can be inaccurate. Double check important info.</p>
        </div>
    )
}
