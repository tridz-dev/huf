"use client";

import { useCallback, useState, useMemo, useEffect, useRef } from 'react';
import { MicIcon } from 'lucide-react';
import { nanoid } from 'nanoid';
import { toast } from 'sonner';
import type { ToolUIPart } from 'ai';
import type { StickToBottomContext } from 'use-stick-to-bottom';

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
  PromptInputActionAddAttachments,
  PromptInputActionMenu,
  PromptInputActionMenuContent,
  PromptInputActionMenuTrigger,
  PromptInputAttachment,
  PromptInputAttachments,
  PromptInputBody,
  PromptInputButton,
  PromptInputFooter,
  PromptInputHeader,
  type PromptInputMessage,
  PromptInputSubmit,
  PromptInputTextarea,
  PromptInputTools,
} from '@/components/ai-elements/prompt-input';

import { AgentModelSelector } from '@/components/chat/AgentModelSelector';

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
  type ChatMessage,
  type ConversationMessageListParams,
} from '@/services/chatApi';
import { useInfiniteScroll } from '@/hooks/useInfiniteScroll';

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
    name: string;
    description: string;
    status: ToolUIPart['state'];
    parameters: Record<string, unknown>;
    result: string | undefined;
    error: string | undefined;
  }[];
};

const initialMessages: MessageType[] = [
  {
    key: nanoid(),
    from: 'user',
    versions: [
      {
        id: nanoid(),
        content: 'hi',
      },
    ],
  },
  {
    key: nanoid(),
    from: 'assistant',
    versions: [
      {
        id: nanoid(),
        content: 'Hello! How can I assist you today?',
      },
    ],
  },
  {
    key: nanoid(),
    from: 'user',
    versions: [
      {
        id: nanoid(),
        content: 'how are yo?',
      },
    ],
  },
  {
    key: nanoid(),
    from: 'assistant',
    versions: [
      {
        id: nanoid(),
        content: "I'm doing well, thank you! How about you?",
      },
    ],
  },
];


const mockResponses = [
  "That's a great question! Let me help you understand this concept better.",
  "I'd be happy to explain this topic in detail. There are several important factors to consider.",
  'This is an interesting topic that comes up frequently. The solution typically involves understanding the core concepts.',
  'Great choice of topic! This is something that many developers encounter.',
  "That's definitely worth exploring. The best way to handle this is to consider both theoretical and practical aspects.",
];

interface ChatWindowProps {
  chatId: string | null;
}

export function ChatWindow({ chatId }: ChatWindowProps) {
  const [model, setModel] = useState<string>('');
  const [modelName, setModelName] = useState<string>('');
  const [text, setText] = useState<string>('');
  // const [useWebSearch, setUseWebSearch] = useState<boolean>(false);
  const [useMicrophone, setUseMicrophone] = useState<boolean>(false);
  const [status, setStatus] = useState<'submitted' | 'streaming' | 'ready' | 'error'>('ready');
  const [messages, setMessages] = useState<MessageType[]>(initialMessages);
  const stickContextRef = useRef<StickToBottomContext | null>(null);
  const lastMessageIdRef = useRef<string | null>(null);

  const isNewChat = !chatId;
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

  useEffect(() => {
    if (!chatId) {
      setMessages(initialMessages);
      return;
    }

    const mapped: MessageType[] = conversationItems.map((item) => ({
      key: item.id,
      from: item.isAgent ? 'assistant' : 'user',
      versions: [
        {
          id: item.id,
          content: item.content,
        },
      ],
    }));

    setMessages(mapped);
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

  useEffect(() => {
    if (isNewChat || messagesLoading || messages.length === 0) {
      const lastId = messages[messages.length - 1]?.key ?? null;
      lastMessageIdRef.current = lastId;
      return;
    }

    const lastId = messages[messages.length - 1]?.key ?? null;

    if (lastId && lastId !== lastMessageIdRef.current) {
      stickContextRef.current?.scrollToBottom();
    }

    lastMessageIdRef.current = lastId;
  }, [isNewChat, messagesLoading, messages]);

  const streamResponse = useCallback(
    async (messageId: string, content: string) => {
      setStatus('streaming');
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
        await new Promise((resolve) => setTimeout(resolve, Math.random() * 100 + 50));
      }

      setStatus('ready');
    },
    []
  );

  const addUserMessage = useCallback(
    (content: string) => {
      const userMessage: MessageType = {
        key: `user-${Date.now()}`,
        from: 'user',
        versions: [
          {
            id: `user-${Date.now()}`,
            content,
          },
        ],
      };

      setMessages((prev) => [...prev, userMessage]);

      setTimeout(() => {
        const assistantMessageId = `assistant-${Date.now()}`;
        const randomResponse = mockResponses[Math.floor(Math.random() * mockResponses.length)];

        const assistantMessage: MessageType = {
          key: `assistant-${Date.now()}`,
          from: 'assistant',
          versions: [
            {
              id: assistantMessageId,
              content: '',
            },
          ],
        };

        setMessages((prev) => [...prev, assistantMessage]);
        streamResponse(assistantMessageId, randomResponse);
      }, 500);
    },
    [streamResponse]
  );

  const handleSubmit = (message: PromptInputMessage) => {
    const hasText = Boolean(message.text);
    const hasAttachments = Boolean(message.files?.length);

    if (!(hasText || hasAttachments)) {
      return;
    }

    setStatus('submitted');

    if (message.files?.length) {
      toast.success('Files attached', {
        description: `${message.files.length} file(s) attached to message`,
      });
    }

    addUserMessage(message.text || 'Sent with attachments');
    setText('');
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
          {isNewChat ? (
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

                          <MessageContent>
                            <MessageResponse>{version.content}</MessageResponse>
                          </MessageContent>
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
              <PromptInputHeader>
                <PromptInputAttachments>
                  {(attachment) => <PromptInputAttachment data={attachment} />}
                </PromptInputAttachments>
              </PromptInputHeader>

              <PromptInputBody>
                <PromptInputTextarea onChange={(event) => setText(event.target.value)} value={text} />
              </PromptInputBody>

              <PromptInputFooter>
                <PromptInputTools>
                  <PromptInputActionMenu>
                    <PromptInputActionMenuTrigger />
                    <PromptInputActionMenuContent>
                      <PromptInputActionAddAttachments />
                    </PromptInputActionMenuContent>
                  </PromptInputActionMenu>

                  <PromptInputButton
                    onClick={() => setUseMicrophone(!useMicrophone)}
                    variant={useMicrophone ? 'default' : 'ghost'}
                  >
                    <MicIcon size={16} />
                    <span className="sr-only">Microphone</span>
                  </PromptInputButton>

                  {/* <PromptInputButton
                    onClick={() => setUseWebSearch(!useWebSearch)}
                    variant={useWebSearch ? 'default' : 'ghost'}
                  >
                    <GlobeIcon size={16} />
                    <span>Search</span>
                  </PromptInputButton> */}

                  <AgentModelSelector
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

