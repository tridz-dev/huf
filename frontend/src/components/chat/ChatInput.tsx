import { useState, useRef, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { CornerDownLeft, Plus, Paperclip } from "lucide-react";
import { Button } from "../ui/button";
import { Textarea } from "../ui/textarea";
import { ShortcutKey } from "../ui/shortcut-key";
import {
  sendMessage,
  streamingAvailable,
  setStreamingAvailable,
} from "@/services/streamChatApi";
import { transcribeAudio, prepareMessageWithFile, uploadFileAttachment } from "@/services/chatApi";
import type { PrepareMessageWithFileFile } from "@/services/chatApi";
import { SpeechInput } from "@/components/ai-elements/speech-input";
import { ChatAttachmentCard } from "@/components/chat/ChatAttachmentCard";
import { getFileTypeInfo } from "@/utils/fileTypeUtils";
import { getFrappeErrorMessage } from "@/lib/frappe-error";
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
    allowFileUpload?: boolean;
    maxUploadSizeMb?: number | null;
    /**
     * Agent policy: run turns directly (no queue). When true and the SSE
     * endpoint is reachable, the chat streams; otherwise turns are
     * queue-first.
     */
    runImmediately?: boolean;
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
    allowFileUpload = false,
    maxUploadSizeMb,
    runImmediately = false,
}: ChatInputProps) {
    const navigate = useNavigate();
    const [message, setMessage] = useState('');
    const [isSubmitting, setIsSubmitting] = useState(false);
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const isAudioRecordingFlowRef = useRef(false);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const [pendingFile, setPendingFile] = useState<{
        file: File;
        name: string;
        fileId?: string;
        fileUrl?: string;
        status: 'uploading' | 'ready' | 'error';
        error?: string;
    } | null>(null);
    
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
            skipUserMessage?: boolean;
            files?: PrepareMessageWithFileFile[];
        }) => {
            // Queue-first by default: turns go through the REST path and
            // reconcile from run lifecycle socket events. SSE streaming is the
            // explicit direct-execution mode, used only for agents with the
            // advanced `run_immediately` policy when the stream endpoint is
            // reachable.
            const useStreaming = streamingAvailable && runImmediately;
            const response = await sendMessage(
                {
                    agent: agentName,
                    message: params.message,
                    conversationId: params.conversationId,
                    skipUserMessage: params.skipUserMessage,
                    files: params.files,
                },
                {
                    useStreaming,
                    onDelta: useStreaming ? params.updateAssistantContent : undefined,
                    skipUserMessage: params.skipUserMessage,
                    files: params.files,
                }
            );
            const msg = response.message as Record<string, unknown>;
            const conversationId =
                (msg?.conversation_id as string) ??
                ((msg?.run as Record<string, unknown>)?.conversation_id as string);
            const responseTextRaw =
                (msg?.run as Record<string, unknown>)?.response ?? msg?.response;
            const responseText = typeof responseTextRaw === 'string' ? responseTextRaw : '';
            // `new_conversation` nests the run ack under `msg.run`; `send_message_to_conversation`
            // returns it flattened at the top level. Check both, like the other run fields below —
            // otherwise the very first message in a brand-new conversation is never marked queued,
            // so the pending bubble never gets `runStatus` and the polling fallback never engages.
            const queued =
                msg?.queued === true || (msg?.run as Record<string, unknown>)?.queued === true;
            if (!useStreaming && responseText && !queued) {
                params.updateAssistantContent(responseText);
            }
            const agentMessageId =
                (msg?.agent_message_id as string) ||
                ((msg?.run as Record<string, unknown>)?.agent_message_id as string) ||
                undefined;
            const agentRunId =
                (msg?.agent_run_id as string) ||
                ((msg?.run as Record<string, unknown>)?.agent_run_id as string) ||
                undefined;
            const status =
                (msg?.status as string | undefined) ??
                ((msg?.run as Record<string, unknown>)?.status as string | undefined);
            return { conversationId, agentMessageId, agentRunId, queued, status };
        },
        [agentName, runImmediately]
    );

    const syncAssistantMessageId = useCallback(
        (tempId: string, realId: string, content?: string) => {
            setMessages((prev) =>
                prev.map((msg) => {
                    if (msg.key !== tempId) return msg;
                    const existingContent = content ?? msg.versions[0]?.content ?? '';
                    return {
                        ...msg,
                        key: realId,
                        versions: [{ id: realId, content: existingContent }],
                    };
                })
            );
        },
        [setMessages]
    );

    const readFileAsBase64 = useCallback((file: File): Promise<string> => {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onloadend = () => {
                const result = reader.result as string;
                resolve(result.includes(',') ? result.split(',')[1] : result ?? '');
            };
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
    }, []);

    const handleSubmit = useCallback(async (e: React.FormEvent) => {
        e.preventDefault();

        const hasStagedFile = pendingFile?.status === 'ready' && !!pendingFile.fileId;
        if ((!message.trim() && !hasStagedFile) || !agentName || isSubmitting || pendingFile?.status === 'uploading') {
            return;
        }

        if (hasStagedFile && pendingFile?.fileId) {
            const stagedFile = pendingFile.file;
            const messageText = message.trim();
            const displayContent = messageText || `📎 ${pendingFile.name}`;
            const typeInfo = getFileTypeInfo(stagedFile);
            const previewUrl = typeInfo.isImage ? URL.createObjectURL(stagedFile) : undefined;

            setIsSubmitting(true);
            onStatusChange('submitted');

            const userMessageKey = `user-${Date.now()}`;
            const userMessage: MessageType = {
                key: userMessageKey,
                from: 'user',
                versions: [{ id: userMessageKey, content: displayContent }],
                attachment: {
                    name: pendingFile.name,
                    label: typeInfo.label,
                    previewUrl,
                },
            };
            setMessages((prev) => [...prev, userMessage]);
            setMessage('');
            const sentFileId = pendingFile.fileId;
            const sentFileName = pendingFile.name;
            setPendingFile(null);

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
            let assistantKey = assistantMessageId;

            try {
                const prepareRes = await prepareMessageWithFile({
                    file_id: sentFileId,
                    filename: sentFileName,
                    agent: agentName,
                    conversation: chatId ?? undefined,
                    message: messageText,
                });

                if (!prepareRes?.success || !prepareRes.agent_prompt) {
                    throw new Error(
                        typeof prepareRes?.error === 'string'
                            ? prepareRes.error
                            : getFrappeErrorMessage(prepareRes?.error) || 'Failed to prepare file'
                    );
                }

                setPendingFile(null);
                if (!chatId) isCreatingConversationRef.current = true;

                const { conversationId, agentMessageId, agentRunId, queued } = await runAgentAndUpdateAssistant({
                    message: prepareRes.agent_prompt,
                    conversationId: prepareRes.conversation_id ?? chatId ?? undefined,
                    assistantMessageId,
                    updateAssistantContent,
                    skipUserMessage: true,
                    files: prepareRes.files,
                });

                assistantKey = (queued && agentRunId) ? agentRunId : assistantMessageId;
                if (queued && agentRunId) {
                    setMessages((prev) =>
                        prev.map((msg) =>
                            msg.key === assistantMessageId
                                ? { ...msg, key: agentRunId, runStatus: 'Queued' as const, versions: [{ id: agentRunId, content: '' }] }
                                : msg
                        )
                    );
                }

                if (agentMessageId && !queued) {
                    syncAssistantMessageId(assistantKey, agentMessageId);
                }
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
                setPendingFile({
                    file: stagedFile,
                    name: sentFileName,
                    fileId: sentFileId,
                    status: 'error',
                    error: error instanceof Error ? error.message : 'Failed to send file',
                });
                setMessages((prev) =>
                    prev.filter((msg) => msg.key !== userMessageKey && msg.key !== assistantKey)
                );
                toast.error('Failed to send message with attachment', {
                    description: error instanceof Error ? error.message : 'An error occurred',
                });
            } finally {
                setIsSubmitting(false);
            }
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

        let assistantKey = assistantMessageId;
        try {
            if (!chatId) isCreatingConversationRef.current = true;
            const { conversationId, agentMessageId, agentRunId, queued } = await runAgentAndUpdateAssistant({
                message: messageText,
                conversationId: chatId ?? undefined,
                assistantMessageId,
                updateAssistantContent,
            });
            assistantKey = (queued && agentRunId) ? agentRunId : assistantMessageId;
            if (queued && agentRunId) {
                setMessages((prev) =>
                    prev.map((msg) =>
                        msg.key === assistantMessageId
                            ? { ...msg, key: agentRunId, runStatus: 'Queued' as const, versions: [{ id: agentRunId, content: '' }] }
                            : msg
                    )
                );
            }
            if (agentMessageId && !queued) {
                syncAssistantMessageId(assistantKey, agentMessageId);
            }
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
            setMessages((prev) => prev.filter((msg) => msg.key !== assistantKey));
        } finally {
            setIsSubmitting(false);
        }
    }, [message, agentName, chatId, pendingFile, onConversationCreated, isSubmitting, onStatusChange, isCreatingConversationRef, newlyCreatedConversationIdRef, setMessages, scrollToBottomAfterPaint, runAgentAndUpdateAssistant, syncAssistantMessageId]);

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
            let currentAssistantKey = assistantMessageId;
            try {
                // The transcribe endpoint already persisted the user message;
                // skip persisting it again in the run (queue-first workers
                // otherwise add a second user message).
                const { agentMessageId, agentRunId, queued } = await runAgentAndUpdateAssistant({
                    message: res.transcript,
                    conversationId: res.conversation_id,
                    assistantMessageId,
                    updateAssistantContent,
                    skipUserMessage: true,
                });
                currentAssistantKey = (queued && agentRunId) ? agentRunId : assistantMessageId;
                if (queued && agentRunId) {
                    setMessages((prev) =>
                        prev.map((msg) =>
                            msg.key === assistantMessageId
                                ? { ...msg, key: agentRunId, runStatus: 'Queued' as const, versions: [{ id: agentRunId, content: '' }] }
                                : msg
                        )
                    );
                }
                if (agentMessageId && !queued) {
                    syncAssistantMessageId(currentAssistantKey, agentMessageId);
                }
                onStatusChange('ready');
                if (res.conversation_id && onConversationCreated) {
                    newlyCreatedConversationIdRef.current = res.conversation_id;
                    onConversationCreated(res.conversation_id, agentName);
                }
                return res.transcript;
            } catch (agentErr) {
                isCreatingConversationRef.current = false;
                setMessages((prev) => prev.filter((m) => m.key !== currentAssistantKey));
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
    }, [agentName, chatId, onConversationCreated, onStatusChange, onLoadingTypeChange, isCreatingConversationRef, newlyCreatedConversationIdRef, setMessages, scrollToBottomAfterPaint, runAgentAndUpdateAssistant, syncAssistantMessageId]);

    const handleTranscriptionChange = useCallback((text: string) => {
        if (isAudioRecordingFlowRef.current) {
            isAudioRecordingFlowRef.current = false;
            return;
        }
        setMessage((prev) => (prev ? `${prev} ${text}` : text));
    }, []);

    const handleFileSelected = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        e.target.value = '';
        if (!file || !agentName) return;

        const sizeLimitMb = maxUploadSizeMb ?? 25;
        if (file.size > sizeLimitMb * 1024 * 1024) {
            toast.error(`File exceeds the maximum size of ${sizeLimitMb} MB.`);
            return;
        }

        setPendingFile({ file, name: file.name, status: 'uploading' });

        try {
            const b64 = await readFileAsBase64(file);
            const res = await uploadFileAttachment({
                filename: file.name,
                b64data: b64,
                agent: agentName,
            });

            if (!res?.success || !res.file_id) {
                setPendingFile({
                    file,
                    name: file.name,
                    status: 'error',
                    error: typeof res?.error === 'string'
                        ? res.error
                        : getFrappeErrorMessage(res?.error) || 'Upload failed',
                });
                return;
            }

            setPendingFile({
                file,
                name: file.name,
                fileId: res.file_id,
                fileUrl: res.file_url,
                status: 'ready',
            });
            textareaRef.current?.focus();
        } catch (err) {
            setPendingFile({
                file,
                name: file.name,
                status: 'error',
                error: getFrappeErrorMessage(err) || (err instanceof Error ? err.message : 'Upload failed'),
            });
        }
    }, [agentName, maxUploadSizeMb, readFileAsBase64]);

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
                    {pendingFile && (
                        <div className="px-3 pt-2 w-full">
                            <ChatAttachmentCard
                                name={pendingFile.name}
                                file={pendingFile.file}
                                status={pendingFile.status}
                                error={pendingFile.error}
                                onRemove={
                                    pendingFile.status !== 'uploading'
                                        ? () => setPendingFile(null)
                                        : undefined
                                }
                            />
                        </div>
                    )}
                    <div className="px-3 pb-3 w-full flex items-center justify-end gap-x-2 mt-2">
                        <span className="flex items-center gap-x-1 text-[10px] text-zinc-400">
                            Use
                            <ShortcutKey>
                                Shift + Enter
                            </ShortcutKey>
                            for new line
                        </span>
                        {allowFileUpload && (
                            <>
                                <input
                                    ref={fileInputRef}
                                    type="file"
                                    accept="image/*,.pdf,.docx,.xlsx,.pptx,.txt,.md,.csv,.json,.xml,.html,.htm"
                                    className="hidden"
                                    onChange={handleFileSelected}
                                    disabled={isSubmitting || isModelMismatch || pendingFile?.status === 'uploading'}
                                />
                                <Button
                                    type="button"
                                    variant="secondary"
                                    size="icon"
                                    className="shrink-0 rounded-full"
                                    disabled={isSubmitting || isModelMismatch || pendingFile?.status === 'uploading'}
                                    onClick={() => fileInputRef.current?.click()}
                                    aria-label="Attach file"
                                >
                                    <Paperclip className="size-4" />
                                </Button>
                            </>
                        )}
                        {!message.trim() && !pendingFile && (
                            <SpeechInput
                                onTranscriptionChange={handleTranscriptionChange}
                                onAudioRecorded={handleAudioRecorded}
                                disabled={isSubmitting || isModelMismatch}
                                size="icon"
                                className="shrink-0 rounded-full"
                            />
                        )}
                        <Button
                            type="submit"
                            disabled={
                                pendingFile?.status === 'uploading' ||
                                ((!message.trim() && !(pendingFile?.status === 'ready' && pendingFile.fileId)) ||
                                    isSubmitting ||
                                    isModelMismatch)
                            }
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
