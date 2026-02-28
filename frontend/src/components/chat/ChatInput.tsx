import { useState, useRef, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { CornerDownLeft, Plus } from "lucide-react";
import { Button } from "../ui/button";
import { Textarea } from "../ui/textarea";
import { ShortcutKey } from "../ui/shortcut-key";
import {
  sendMessage,
  streamingAvailable,
  setStreamingAvailable,
} from "@/services/streamChatApi";
import type { MessageType } from './types';

interface ChatInputProps {
    chatId: string | null;
    agentName: string;
    onConversationCreated?: (conversationId: string, agentName?: string) => void;
    onStatusChange: (status: 'submitted' | 'streaming' | 'ready' | 'error') => void;
    isCreatingConversationRef: React.MutableRefObject<boolean>;
    newlyCreatedConversationIdRef: React.MutableRefObject<string | null>;
    setMessages: React.Dispatch<React.SetStateAction<MessageType[]>>;
    isModelMismatch?: boolean;
    scrollToBottomAfterPaint?: (instant?: boolean) => void;
}

export function ChatInput({ 
    chatId, 
    agentName,
    onConversationCreated,
    onStatusChange,
    isCreatingConversationRef,
    newlyCreatedConversationIdRef,
    setMessages,
    isModelMismatch = false,
    scrollToBottomAfterPaint,
}: ChatInputProps) {
    const navigate = useNavigate();
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

        const assistantMessageId = `assistant-${Date.now()}`;
        const assistantMessage: MessageType = {
            key: assistantMessageId,
            from: 'assistant',
            versions: [{ id: assistantMessageId, content: '' }],
        };
        setMessages((prev) => [...prev, assistantMessage]);

        const updateAssistantContent = (content: string) => {
            setMessages((prev) =>
                prev.map((msg) =>
                    msg.key === assistantMessageId
                        ? {
                              ...msg,
                              versions: [{ id: assistantMessageId, content }],
                          }
                        : msg
                )
            );
            scrollToBottomAfterPaint?.(false);
        };

        try {
            if (!chatId) {
                isCreatingConversationRef.current = true;
            }

            const useStreaming = streamingAvailable;
            const response = await sendMessage(
                {
                    agent: agentName,
                    message: messageText,
                    conversationId: chatId ?? undefined,
                },
                {
                    useStreaming,
                    onDelta:
                        useStreaming
                            ? (text) => updateAssistantContent(text)
                            : undefined,
                }
            );

            const msg = response.message as Record<string, unknown>;
            const conversationId =
                (msg?.conversation_id as string) ??
                ((msg?.run as Record<string, unknown>)?.conversation_id as string);
            const responseTextRaw =
                (msg?.run as Record<string, unknown>)?.response ?? msg?.response;
            const responseText =
                typeof responseTextRaw === 'string' ? responseTextRaw : '';

            if (!useStreaming && responseText) {
                updateAssistantContent(responseText);
            }
            onStatusChange('ready');

            if (conversationId && onConversationCreated) {
                newlyCreatedConversationIdRef.current = conversationId;
                onConversationCreated(conversationId, agentName);
                setTimeout(() => {
                    isCreatingConversationRef.current = false;
                }, 500);
            } else {
                isCreatingConversationRef.current = false;
            }

            setTimeout(() => {
                if (textareaRef.current) {
                    textareaRef.current.focus();
                }
            }, chatId ? 100 : 200);
        } catch (error) {
            if (streamingAvailable) {
                setStreamingAvailable(false);
            }
            isCreatingConversationRef.current = false;
            onStatusChange('error');
            toast.error('Failed to send message', {
                description: error instanceof Error ? error.message : 'An error occurred',
            });
            setMessages((prev) =>
                prev.filter((msg) => msg.key !== assistantMessageId)
            );
        } finally {
            setIsSubmitting(false);
        }
    }, [message, agentName, chatId, onConversationCreated, isSubmitting, onStatusChange, isCreatingConversationRef, newlyCreatedConversationIdRef, setMessages, scrollToBottomAfterPaint]);

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

    const handleNewConversation = useCallback(() => {
        if (agentName) {
            navigate(`/chat/new?agent=${agentName}`);
        }
    }, [navigate, agentName]);

    if (!agentName) {
        return null;
    }

    if (isModelMismatch && chatId) {
        return (
            <div className="px-6 pb-6 pt-2">
                <div className="w-full border border-zinc-200 rounded-xl bg-zinc-50 p-6">
                    <div className="flex flex-col items-center justify-center gap-4 text-center">
                        <p className="text-sm text-zinc-600">
                            Model changed, please start a new conversation
                        </p>
                        <Button
                            onClick={handleNewConversation}
                            className="gap-2"
                        >
                            <Plus className="w-4 h-4" />
                            New Conversation
                        </Button>
                    </div>
                </div>
            </div>
        );
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
                        disabled={isSubmitting || isModelMismatch}
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
                            disabled={!message.trim() || isSubmitting || isModelMismatch}
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
    );
}
