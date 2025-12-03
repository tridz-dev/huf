import { useCallback, useState, useMemo, useEffect, useRef } from 'react';
// import { MicIcon } from 'lucide-react';
import { toast } from 'sonner';
import type { ToolUIPart } from 'ai';
import type { StickToBottomContext } from 'use-stick-to-bottom';
import { useSearchParams } from 'react-router-dom';
import {
  MessageBranch,
  MessageBranchContent,
  MessageBranchNext,
  MessageBranchPage,
  MessageBranchPrevious,
  MessageBranchSelector,
} from '@/components/ai-elements/message';

import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
} from '@/components/ai-elements/conversation';

import { Message, MessageContent } from '@/components/ai-elements/message';

import {
  PromptInput,
  // PromptInputActionAddAttachments,
  // PromptInputActionMenu,
  // PromptInputActionMenuContent,
  // PromptInputActionMenuTrigger,
  PromptInputAttachment,
  PromptInputAttachments,
  PromptInputBody,
  // PromptInputButton,
  PromptInputFooter,
  PromptInputHeader,
  type PromptInputMessage,
  PromptInputSubmit,
  PromptInputTextarea,
  PromptInputTools,
  usePromptInputAttachments,
} from '@/components/ai-elements/prompt-input';

import { AgentModelSelector } from '@/components/chat/AgentModelSelector';
import { MessageActions } from '@/components/chat/MessageActions';

import {
  Reasoning,
  ReasoningContent,
  ReasoningTrigger,
} from '@/components/ai-elements/reasoning';

import { MessageResponse } from '@/components/ai-elements/message';

import {
  Source,
  Sources,
  SourcesContent,
  SourcesTrigger,
} from '@/components/ai-elements/sources';

// import { Suggestion, Suggestions } from '@/components/ai-elements/suggestion';
import {
  getConversationMessages,
  getConversation,
  newConversation,
  sendMessageToConversation,
  createAgentRunFeedback,
  type ChatMessage,
  type ConversationMessageListParams,
} from '@/services/chatApi';
import { useInfiniteScroll } from '@/hooks/useInfiniteScroll';
import { Tool, ToolHeader, ToolContent, ToolInput, ToolOutput } from '@/components/ai-elements/tool';
import type { ExtendedToolState } from '@/components/ai-elements/types';
import { useChatSocket, type ToolCallEvent } from '@/hooks/useChatSocket';

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
  sources?: { href: string; title: string }[];
  versions: {
    id: string;
    content: string;
  }[];
  reasoning?: {
    content: string;
    duration: number;
  };
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
  chatId: string | null;
  onConversationCreated?: (conversationId: string) => void;
}

// Component to conditionally render header only when there are attachments
function ConditionalPromptInputHeader() {
  const attachments = usePromptInputAttachments();
  
  if (attachments.files.length === 0) {
    return null;
  }
  
  return (
    <PromptInputHeader>
      <PromptInputAttachments>
        {(attachment) => <PromptInputAttachment data={attachment} />}
      </PromptInputAttachments>
    </PromptInputHeader>
  );
}

export function ChatWindow({ chatId, onConversationCreated }: ChatWindowProps) {
  const [searchParams] = useSearchParams();
  const [model, setModel] = useState<string>(() => searchParams.get('agent') ?? '');
  const [modelName, setModelName] = useState<string>('');
  const [text, setText] = useState<string>('');
  // const [useWebSearch, setUseWebSearch] = useState<boolean>(false);
  // const [useMicrophone, setUseMicrophone] = useState<boolean>(false);
  const [status, setStatus] = useState<'submitted' | 'streaming' | 'ready' | 'error'>('ready');
  const [messages, setMessages] = useState<MessageType[]>([]);
  const stickContextRef = useRef<StickToBottomContext | null>(null);
  const lastMessageIdRef = useRef<string | null>(null);

  let isNewChat = !chatId;
  const messageParams = useMemo(() => {
    if (!chatId) {
      return {} as Omit<ConversationMessageListParams, 'page' | 'limit' | 'start'>;
    }
    return {
      conversation: chatId,
    } satisfies Omit<ConversationMessageListParams, 'page' | 'limit' | 'start'>;
  }, [chatId]);

  const {
    items: conversationItems,
    initialLoading: messagesLoading,
    loadingMore: messagesLoadingMore,
    hasMore: messagesHasMore,
    error: messagesError,
    sentinelRef: messagesSentinelRef,
    scrollRef: messagesScrollRef,
  } = useInfiniteScroll<ConversationMessageListParams, ChatMessage>({
    fetchFn: getConversationMessages,
    initialParams: messageParams,
    pageSize: 30,
    direction: 'reverse',
    enabled: Boolean(chatId),
    autoLoad: Boolean(chatId),
    autoLoadMore: Boolean(chatId),
  });

  // Track if we're in the middle of creating a new conversation
  const isCreatingConversationRef = useRef(false);

  // Handle tool updates from socket
  const handleToolUpdate = useCallback((event: ToolCallEvent) => {
    // Only process events for the current conversation
    if (event.conversation_id !== chatId) {
      return;
    }

    setMessages((prev) => {
      // Parse tool data
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

      // Find message by message_id
      const messageIndex = prev.findIndex((msg) => 
        msg.versions.some((v) => v.id === event.message_id)
      );

      if (messageIndex >= 0) {
        // Message exists - update or add tool by tool_call_id
        const message = prev[messageIndex];
        const existingTools = message.tools || [];
        const toolIndex = existingTools.findIndex(
          (tool) => tool.tool_call_id === event.tool_call_id
        );

        const updatedTools = [...existingTools];
        if (toolIndex >= 0) {
          updatedTools[toolIndex] = updatedTool;
        } else {
          updatedTools.push(updatedTool);
        }

        const updated = [...prev];
        updated[messageIndex] = {
          ...message,
          tools: updatedTools,
        };
        return updated;
      } else {
        // Message doesn't exist - create new message with tool
        const newMessage: MessageType = {
          key: event.message_id,
          from: 'assistant',
          versions: [
            {
              id: event.message_id,
              content: '',
            },
          ],
          tools: [updatedTool],
        };
        return [...prev, newMessage];
      }
    });
  }, [chatId]);

  useChatSocket({
    conversationId: chatId,
    onToolUpdate: handleToolUpdate,
  });

  useEffect(() => {
    if (!chatId) {
      // Only clear messages if we're not creating a conversation
      if (!isCreatingConversationRef.current) {
        setMessages([]);
      }
      return;
    }

    // If we're creating a conversation, don't overwrite local messages yet
    if (isCreatingConversationRef.current) {
      return;
    }

    setMessages((prev) => {
      const mapped: MessageType[] = conversationItems.map((item) => {
        // Check if we have a temporary message for this item (created from socket events)
        const tempMessage = prev.find((msg) => msg.key === item.id);
        const tempTools = tempMessage?.tools || [];

        const baseMessage: MessageType = {
          key: item.id,
          from: item.isAgent ? 'assistant' : 'user',
          versions: [
            {
              id: item.id,
              content: item.content,
            },
          ],
        };

        // Add tool information if this is a Tool Result message
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

          // Use tool_call_id from temp tools if available, otherwise generate one
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

          // Merge: prefer temp tools (from socket) as they're more up-to-date
          const toolMap = new Map<string, typeof apiTool>();
          tempTools.forEach((tool) => {
            toolMap.set(tool.tool_call_id, tool as any);
          });
          
          // Add API tool if no temp tool with same tool_call_id exists
          if (!toolMap.has(tool_call_id)) {
            toolMap.set(tool_call_id, apiTool);
          }
          
          baseMessage.tools = Array.from(toolMap.values());
        } else if (tempTools.length > 0) {
          // Message doesn't have tools from API, but we have temporary tools from socket
          baseMessage.tools = tempTools;
        }

        return baseMessage;
      });

      // Add any temporary messages that aren't in the API response yet
      const apiMessageIds = new Set(conversationItems.map((item) => item.id));
      const remainingTempMessages = prev.filter(
        (msg) => !apiMessageIds.has(msg.key) && msg.tools && msg.tools.length > 0
      );

      return [...mapped, ...remainingTempMessages];
    });
  }, [chatId, conversationItems]);


  const handleConversationContext = useCallback(
    (ctx: StickToBottomContext | null) => {
      stickContextRef.current = ctx;
      // Try to get scroll element from context, or find it from contentRef
      const scrollElement = ctx?.scrollRef?.current ?? ctx?.contentRef?.current?.parentElement;
      
      // Verify that the element is actually scrollable
      if (scrollElement instanceof HTMLElement) {
        const style = window.getComputedStyle(scrollElement);
        const isScrollable =
          style.overflowY === 'auto' ||
          style.overflowY === 'scroll' ||
          style.overflow === 'auto' ||
          style.overflow === 'scroll';
        
        if (isScrollable) {
          messagesScrollRef.current = scrollElement as HTMLDivElement;
        } else {
          // If not scrollable, try to find scrollable parent
          let parent = scrollElement.parentElement;
          while (parent) {
            const parentStyle = window.getComputedStyle(parent);
            if (
              parentStyle.overflowY === 'auto' ||
              parentStyle.overflowY === 'scroll' ||
              parentStyle.overflow === 'auto' ||
              parentStyle.overflow === 'scroll'
            ) {
              messagesScrollRef.current = parent as HTMLDivElement;
              break;
            }
            parent = parent.parentElement;
          }
        }
      } else {
        messagesScrollRef.current = null;
      }
    },
    [messagesScrollRef]
  );

  // Ensure scrollRef is set from sentinel's scrollable parent if not already set
  useEffect(() => {
    if (!messagesSentinelRef.current || messagesScrollRef.current) {
      return;
    }

    // Find scrollable parent of sentinel
    let parent = messagesSentinelRef.current.parentElement;
    while (parent) {
      const style = window.getComputedStyle(parent);
      if (
        style.overflowY === 'auto' ||
        style.overflowY === 'scroll' ||
        style.overflow === 'auto' ||
        style.overflow === 'scroll'
      ) {
        messagesScrollRef.current = parent as HTMLDivElement;
        break;
      }
      parent = parent.parentElement;
    }
  }, [messagesSentinelRef, messagesScrollRef, messages.length, chatId]);

  // Scroll to bottom when chat changes or messages are loaded
  useEffect(() => {
    if (isNewChat || messagesLoading || messages.length === 0) {
      const lastId = messages[messages.length - 1]?.key ?? null;
      lastMessageIdRef.current = lastId;
      return;
    }

    const lastId = messages[messages.length - 1]?.key ?? null;

    // Scroll if: new message added OR chat switched (lastMessageIdRef is null)
    if (lastId && (lastId !== lastMessageIdRef.current || lastMessageIdRef.current === null)) {
      // Use requestAnimationFrame and setTimeout to ensure DOM is ready
      requestAnimationFrame(() => {
        stickContextRef.current?.scrollToBottom();
        // Fallback scroll after a short delay
        setTimeout(() => {
          stickContextRef.current?.scrollToBottom();
        }, 50);
      });
    }

    lastMessageIdRef.current = lastId;
  }, [isNewChat, messagesLoading, messages]);

  // Reset state when switching chats
  const previousChatIdRef = useRef<string | null>(chatId);
  useEffect(() => {
    if (chatId && chatId !== previousChatIdRef.current) {
      // Clear messages when conversation changes to prevent showing messages from previous conversation
      setMessages([]);
      // Reset agent selection when conversation changes
      setModel('');
      setModelName('');
      // Reset last message ID when switching chats to force scroll to bottom
      lastMessageIdRef.current = null;
    }
    previousChatIdRef.current = chatId;
  }, [chatId]);

  useEffect(() => {
    if (chatId) {
      getConversation(chatId)
        .then((conversation) => {
          if (conversation?.agent) {
            // Always update when conversation changes
            setModel(conversation.agent);
            setModelName(conversation.agent);
          }
        })
        .catch((error) => {
          console.error('Failed to load conversation agent', error);
        });
      return;
    }
    // For new chats, use agent from query params
    const agentFromQuery = searchParams.get('agent') ?? '';
    if (agentFromQuery) {
      setModel(agentFromQuery);
    } else {
      // Clear if no agent in query and no chatId
      setModel('');
      setModelName('');
    }
  }, [chatId, searchParams]);

  const handleFeedback = useCallback(
    async (
      feedbackType: 'Thumbs Up' | 'Thumbs Down',
      options?: { agentMessageId?: string; comments?: string }
    ) => {
      if (!model) {
        toast.error('Select an agent before submitting feedback');
        return;
      }

      try {
        await createAgentRunFeedback({
          agent: model,
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
    [model, chatId]
  );

  const streamResponse = useCallback(
    async (messageId: string, content: string) => {
      setStatus('streaming');
      
      // Scroll to bottom when streaming starts
      requestAnimationFrame(() => {
        stickContextRef.current?.scrollToBottom();
      });
      
      const words = content.split(' ');
      let currentContent = '';

      for (let i = 0; i < words.length; i++) {
        currentContent += (i > 0 ? ' ' : '') + words[i];
        setMessages((prev) =>
          prev.map((msg) => {
            if (msg.versions.some((v) => v.id === messageId)) {
              return {
                ...msg,
                versions: msg.versions.map((v) =>
                  v.id === messageId ? { ...v, content: currentContent } : v
                ),
              };
            }
            return msg;
          })
        );
        
        // Scroll after each word update to keep up with growing content
        requestAnimationFrame(() => {
          stickContextRef.current?.scrollToBottom();
        });
        
        await new Promise((resolve) => setTimeout(resolve, Math.random() * 100 + 50));
      }

      setStatus('ready');
      
      // Scroll to bottom again when streaming completes
      requestAnimationFrame(() => {
        stickContextRef.current?.scrollToBottom();
      });
    },
    []
  );

  const handleSubmit = async (message: PromptInputMessage) => {
    const hasText = Boolean(message.text);
    const hasAttachments = Boolean(message.files?.length);

    if (!(hasText || hasAttachments)) {
      return;
    }
    setText('');
    setStatus('submitted');

    if (message.files?.length) {
      toast.success('Files attached', {
        description: `${message.files.length} file(s) attached to message`,
      });
    }

    const messageText = message.text || 'Sent with attachments';

    // Check if we have an agent selected
    if (!model) {
      toast.error('Please select an agent first');
      setText(messageText);
      setStatus('ready');
      return;
    }

    // For new conversations, create conversation first
    if (!chatId) {
      let assistantMessageId: string | null = null;
      
      try {
        // Mark that we're creating a conversation to prevent message overwrite
        isCreatingConversationRef.current = true;
        isNewChat = false;
        // Add user message immediately - use a stable key
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

        // Scroll to show user message immediately
        requestAnimationFrame(() => {
          stickContextRef.current?.scrollToBottom();
        });

        // Add placeholder assistant message
        assistantMessageId = `assistant-${Date.now()}`;
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

        // Call the new conversation API
        const response = await newConversation({
          agent: model,
          message: messageText,
        });

        // Get conversation ID and response
        const conversationId = response.message?.conversation_id;
        const responseText = response.message?.run?.response;

        // Stream the response BEFORE navigating to preserve messages
        if (responseText && assistantMessageId) {
          await streamResponse(assistantMessageId, responseText);
        } else {
          setStatus('ready');
        }

        // Navigate to the new conversation AFTER streaming completes
        if (conversationId && onConversationCreated) {
          // Reset the flag after a short delay to allow navigation to complete
          setTimeout(() => {
            isCreatingConversationRef.current = false;
          }, 100);
          onConversationCreated(conversationId);
        } else {
          isCreatingConversationRef.current = false;
        }

        // Scroll to bottom after response
        requestAnimationFrame(() => {
          stickContextRef.current?.scrollToBottom();
        });
      } catch (error) {
        isCreatingConversationRef.current = false;
        setStatus('error');
        toast.error('Failed to create conversation', {
          description: error instanceof Error ? error.message : 'An error occurred',
        });
        setText(messageText);
        // Remove the placeholder assistant message on error
        if (assistantMessageId) {
          setMessages((prev) => prev.filter((msg) => msg.key !== assistantMessageId));
        }
      }
    } 
    // For existing conversations, use the send message API
    else {
      let assistantMessageId: string | null = null;
      
      try {
        // Add user message immediately
        const userMessage: MessageType = {
          key: `user-${Date.now()}`,
          from: 'user',
          versions: [
            {
              id: `user-${Date.now()}`,
              content: messageText,
            },
          ],
        };
        setMessages((prev) => [...prev, userMessage]);

        // Add placeholder assistant message
        assistantMessageId = `assistant-${Date.now()}`;
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

        // Call the API
        const response = await sendMessageToConversation({
          conversation: chatId,
          message: messageText,
        });

        // Stream the response using streamResponse function
        if (response.message?.response && assistantMessageId) {
          await streamResponse(assistantMessageId, response.message.response);
        } else {
          setStatus('ready');
        }

        // Scroll to bottom after response
        requestAnimationFrame(() => {
          stickContextRef.current?.scrollToBottom();
        });
      } catch (error) {
        setStatus('error');
        toast.error('Failed to send message', {
          description: error instanceof Error ? error.message : 'An error occurred',
        });
        setText(message.text || '');
        // Remove the placeholder assistant message on error
        if (assistantMessageId) {
          setMessages((prev) => prev.filter((msg) => msg.key !== assistantMessageId));
        }
      }
    }
  };

  // const handleSuggestionClick = (suggestion: string) => {
  //   setStatus('submitted');
  //   addUserMessage(suggestion);
  // };

  return (
    <div className="flex h-full w-full flex-col overflow-hidden bg-background">
      {/* Header */}
      <div className="border-b border-border px-4 py-3 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3 shrink-0">
          <h2 className="text-sm font-semibold">
            {modelName ?? 'No model selected'}
          </h2>
        </div>
      </div>

      {/* Conversation - Scrollable Area */}
      {/* <div className="flex-1 min-h-0 flex"> */}
      <Conversation
        className="h-full flex-1 py-4 flex overflow-y-auto"
        contextRef={handleConversationContext}
      >
        <ConversationContent className="flex-1 h-full">
          {(isNewChat && !isCreatingConversationRef.current) ? (
            <div className="flex h-full items-center justify-center px-6">
              <div className="text-center space-y-4 max-w-md">
                <h2 className="text-2xl font-semibold">Hello there!</h2>
                <p className="text-muted-foreground">
                  Start a new conversation
                </p>
              </div>
            </div>
          ) : messagesLoading ? (
            <div className="flex h-full items-center justify-center">
              <p className="text-sm text-muted-foreground">Loading messages...</p>
            </div>
          ) : messagesError ? (
            <div className="flex h-full items-center justify-center">
              <p className="text-sm text-destructive">Failed to load messages</p>
            </div>
          ) : messages.length === 0 ? (
            <div className="flex h-full items-center justify-center">
              <p className="text-sm text-muted-foreground">No messages yet</p>
            </div>
          ) : (
            <>
              {!isNewChat && messagesHasMore && (
                <div
                  ref={messagesSentinelRef}
                  className="h-4 w-full opacity-0 pointer-events-none"
                  aria-hidden="true"
                />
              )}
              {!isNewChat && messagesLoadingMore && (
                <div className="text-xs text-muted-foreground text-center">
                  Loading previous messages...
                </div>
              )}
              {messages.map(({ versions, ...message }) => (
                <MessageBranch defaultBranch={0} key={message.key}>
                  <MessageBranchContent>
                    {versions.map((version) => (
                      <Message from={message.from} key={`${message.key}-${version.id}`}>
                        <div>
                          {message.sources?.length && (
                            <Sources>
                              <SourcesTrigger count={message.sources.length} />
                              <SourcesContent>
                                {message.sources.map((source) => (
                                  <Source href={source.href} key={source.href} title={source.title} />
                                ))}
                              </SourcesContent>
                            </Sources>
                          )}

                          {message.reasoning && (
                            <Reasoning duration={message.reasoning.duration}>
                              <ReasoningTrigger />
                              <ReasoningContent>{message.reasoning.content}</ReasoningContent>
                            </Reasoning>
                          )}

                          {/* Render tool component if this is a tool result message */}
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
                            <MessageContent>
                              <MessageResponse>{version.content}</MessageResponse>
                              {message.from === 'assistant' && version.content && !message.tools && (
                                <MessageActions
                                  content={version.content}
                                  onFeedback={handleFeedback}
                                  agentMessageId={version.id}
                                />
                              )}
                            </MessageContent>
                          )}
                        </div>
                      </Message>
                    ))}
                  </MessageBranchContent>

                  {versions.length > 1 && (
                    <MessageBranchSelector from={message.from}>
                      <MessageBranchPrevious />
                      <MessageBranchPage />
                      <MessageBranchNext />
                    </MessageBranchSelector>
                  )}
                </MessageBranch>
              ))}
            </>
          )}
        </ConversationContent>
        {!isNewChat && <ConversationScrollButton />}
      </Conversation>
      {/* </div> */}

      {/* Input Area - Fixed at Bottom */}
      <div className="shrink-0 border-t border-border bg-background">
        <div className="grid gap-4 p-4">
          {/* <Suggestions className="px-4">
            {suggestions.map((suggestion) => (
              <Suggestion
                key={suggestion}
                onClick={() => handleSuggestionClick(suggestion)}
                suggestion={suggestion}
              />
            ))}
          </Suggestions> */}

          <div className="w-full px-4">
            <PromptInput globalDrop multiple onSubmit={handleSubmit}>
              <ConditionalPromptInputHeader />

              <PromptInputBody>
                <PromptInputTextarea onChange={(event) => setText(event.target.value)} value={text} />
              </PromptInputBody>

              <PromptInputFooter>
                <PromptInputTools>
                  {/* <PromptInputActionMenu>
                    <PromptInputActionMenuTrigger />
                    <PromptInputActionMenuContent>
                      <PromptInputActionAddAttachments />
                    </PromptInputActionMenuContent>
                  </PromptInputActionMenu> */}

                  {/* <PromptInputButton
                    onClick={() => setUseMicrophone(!useMicrophone)}
                    variant={useMicrophone ? 'default' : 'ghost'}
                  >
                    <MicIcon size={16} />
                    <span className="sr-only">Microphone</span>
                  </PromptInputButton> */}

                  {/* <PromptInputButton
                    onClick={() => setUseWebSearch(!useWebSearch)}
                    variant={useWebSearch ? 'default' : 'ghost'}
                  >
                    <GlobeIcon size={16} />
                    <span>Search</span>
                  </PromptInputButton> */}

                  <AgentModelSelector
                    disabled={!isNewChat}
                    value={model}
                    onValueChange={setModel}
                    onModelNameChange={setModelName}
                  />
                </PromptInputTools>

                <PromptInputSubmit
                  disabled={!(text.trim() || status) || status === 'streaming'}
                  status={status}
                />
              </PromptInputFooter>
            </PromptInput>
          </div>
        </div>
      </div>
    </div>
  );
}

