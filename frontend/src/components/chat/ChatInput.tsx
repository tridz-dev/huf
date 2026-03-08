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
import { transcribeAudio } from "@/services/chatApi";
import { SpeechInput } from "@/components/ai-elements/speech-input";
import type { MessageType } from './types';

export type LoadingType = 'default' | 'transcribing';

interface ChatInputProps {
    chatId: string | null;
    agentName: string;
    onConversationCreated?: (conversationId: string, agentName?: string) => void;
    onStatusChange: (status: 'submitted' | 'streaming' | 'ready' | 'error') => void;
    onLoadingTypeChange?: (type: LoadingType) => void;
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
    onLoadingTypeChange,
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
    const isAudioRecordingFlowRef = useRef(false);
    
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

    const runAgentAndUpdateAssistant = useCallback(
        async (params: {
            message: string;
            conversationId: string | undefined;
            assistantMessageId: string;
            updateAssistantContent: (content: string) => void;
        }) => {
            const useStreaming = streamingAvailable;
            const response = await sendMessage(
                {
                    agent: agentName,
                    message: params.message,
                    conversationId: params.conversationId,
                },
                {
                    useStreaming,
                    onDelta: useStreaming ? params.updateAssistantContent : undefined,
                }
            );
            const msg = response.message as Record<string, unknown>;
            const conversationId =
                (msg?.conversation_id as string) ??
                ((msg?.run as Record<string, unknown>)?.conversation_id as string);
            const responseTextRaw =
                (msg?.run as Record<string, unknown>)?.response ?? msg?.response;
            const responseText = typeof responseTextRaw === 'string' ? responseTextRaw : '';
            if (!useStreaming && responseText) {
                params.updateAssistantContent(responseText);
            }
            return { conversationId };
        },
        [agentName]
    );

    const handleSubmit = useCallback(async (e: React.FormEvent) => {
        e.preventDefault();
        
        if (!message.trim() || !agentName || isSubmitting) {
            return;
        }

        const messageText = message.trim();
        setIsSubmitting(true);
        onStatusChange('submitted');

        const userMessageKey = `user-${Date.now()}`;
        const userMessage: MessageType = {
            key: userMessageKey,
            from: 'user',
            versions: [{ id: userMessageKey, content: messageText }],
        };
        setMessages((prev) => [...prev, userMessage]);
        setMessage('');
        if (textareaRef.current) textareaRef.current.focus();

        const assistantMessageId = `assistant-${Date.now()}`;
        setMessages((prev) => [
            ...prev,
            { key: assistantMessageId, from: 'assistant' as const, versions: [{ id: assistantMessageId, content: '' }] },
        ]);

        const updateAssistantContent = (content: string) => {
            setMessages((prev) =>
                prev.map((msg) =>
                    msg.key === assistantMessageId
                        ? { ...msg, versions: [{ id: assistantMessageId, content }] }
                        : msg
                )
            );
            scrollToBottomAfterPaint?.(false);
        };

        try {
            if (!chatId) isCreatingConversationRef.current = true;
            const { conversationId } = await runAgentAndUpdateAssistant({
                message: messageText,
                conversationId: chatId ?? undefined,
                assistantMessageId,
                updateAssistantContent,
            });
            onStatusChange('ready');
            if (conversationId && onConversationCreated) {
                newlyCreatedConversationIdRef.current = conversationId;
                onConversationCreated(conversationId, agentName);
                setTimeout(() => { isCreatingConversationRef.current = false; }, 500);
            } else {
                isCreatingConversationRef.current = false;
            }
            setTimeout(() => textareaRef.current?.focus(), chatId ? 100 : 200);
        } catch (error) {
            if (streamingAvailable) setStreamingAvailable(false);
            isCreatingConversationRef.current = false;
            onStatusChange('error');
            toast.error('Failed to send message', {
                description: error instanceof Error ? error.message : 'An error occurred',
            });
            setMessages((prev) => prev.filter((msg) => msg.key !== assistantMessageId));
        } finally {
            setIsSubmitting(false);
        }
    }, [message, agentName, chatId, onConversationCreated, isSubmitting, onStatusChange, isCreatingConversationRef, newlyCreatedConversationIdRef, setMessages, scrollToBottomAfterPaint, runAgentAndUpdateAssistant]);

    const handleAudioRecorded = useCallback(async (blob: Blob): Promise<string> => {
        const filename = `recording-${Date.now()}.webm`;
        const reader = new FileReader();
        const b64 = await new Promise<string>((resolve, reject) => {
            reader.onloadend = () => {
                const result = reader.result as string;
                const base64 = result.includes(',') ? result.split(',')[1] : result;
                resolve(base64 ?? '');
            };
            reader.onerror = reject;
            reader.readAsDataURL(blob);
        });

        const userMessageKey = `user-${Date.now()}`;
        const assistantMessageId = `assistant-${Date.now()}`;
        setMessages((prev) => [
            ...prev,
            { key: assistantMessageId, from: 'assistant' as const, versions: [{ id: assistantMessageId, content: '' }] },
        ]);
        onStatusChange('submitted');
        onLoadingTypeChange?.('transcribing');

        try {
            const res = await transcribeAudio({
                filename,
                b64data: b64,
                agent: agentName,
                conversation: chatId ?? undefined,
            });
            if (!res?.success || !res.transcript) {
                setMessages((prev) => prev.filter((m) => m.key !== assistantMessageId));
                throw new Error(typeof res?.error === 'string' ? res.error : 'Transcription failed');
            }
            isAudioRecordingFlowRef.current = true;
            setMessages((prev) => {
                const idx = prev.findIndex((m) => m.key === assistantMessageId);
                const userMessage: MessageType = {
                    key: userMessageKey,
                    from: 'user',
                    versions: [{ id: userMessageKey, content: res.transcript! }],
                };
                if (idx < 0) return [...prev, userMessage];
                return [...prev.slice(0, idx), userMessage, ...prev.slice(idx)];
            });
            onLoadingTypeChange?.('default');
            if (!chatId) isCreatingConversationRef.current = true;
            const updateAssistantContent = (content: string) => {
                setMessages((prev) =>
                    prev.map((m) =>
                        m.key === assistantMessageId ? { ...m, versions: [{ id: assistantMessageId, content }] } : m
                    )
                );
                scrollToBottomAfterPaint?.(false);
            };
            try {
                await runAgentAndUpdateAssistant({
                    message: res.transcript,
                    conversationId: res.conversation_id,
                    assistantMessageId,
                    updateAssistantContent,
                });
                onStatusChange('ready');
                if (res.conversation_id && onConversationCreated) {
                    newlyCreatedConversationIdRef.current = res.conversation_id;
                    onConversationCreated(res.conversation_id, agentName);
                }
                return res.transcript;
            } catch (agentErr) {
                isCreatingConversationRef.current = false;
                setMessages((prev) => prev.filter((m) => m.key !== assistantMessageId));
                onStatusChange('error');
                toast.error('Failed to send message', {
                    description: agentErr instanceof Error ? agentErr.message : 'An error occurred',
                });
                throw agentErr;
            }
        } catch (err) {
            onStatusChange('error');
            onLoadingTypeChange?.('default');
            isCreatingConversationRef.current = false;
            toast.error('Failed to transcribe or send', {
                description: err instanceof Error ? err.message : 'An error occurred',
            });
            throw err;
        }
    }, [agentName, chatId, onConversationCreated, onStatusChange, onLoadingTypeChange, isCreatingConversationRef, newlyCreatedConversationIdRef, setMessages, scrollToBottomAfterPaint, runAgentAndUpdateAssistant]);

    const handleTranscriptionChange = useCallback((text: string) => {
        if (isAudioRecordingFlowRef.current) {
            isAudioRecordingFlowRef.current = false;
            return;
        }
        setMessage((prev) => (prev ? `${prev} ${text}` : text));
    }, []);

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
                        <SpeechInput
                            onTranscriptionChange={handleTranscriptionChange}
                            onAudioRecorded={handleAudioRecorded}
                            disabled={isSubmitting || isModelMismatch}
                            size="icon"
                            className="shrink-0 rounded-full"
                        />
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
