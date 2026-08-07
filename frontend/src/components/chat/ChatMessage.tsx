import { Link } from 'react-router-dom';
import { BarChart2 } from 'lucide-react';
import { cn } from "@/lib/utils";
import { Message, MessageContent } from '@/components/ai-elements/message';
import { Tool, ToolHeader, ToolContent, ToolInput, ToolOutput } from '@/components/ai-elements/tool';
import { Reasoning, ReasoningTrigger, ReasoningContent } from '@/components/ai-elements/reasoning';
import type { ToolUIPart } from 'ai';
import { MessageActions } from './MessageActions';
import { MessageLoadingState } from './MessageLoadingState';
import { ChatErrorCard } from './ChatErrorCard';
import { CopyButton } from './CopyButton';
import { Image } from '@/components/ai-elements/image';
import { Video } from '@/components/ai-elements/video';
import { Skeleton } from '@/components/ui/skeleton';
import type { MessageType } from './types';
import { MessageContentWithArtifacts } from './MessageContentWithArtifacts';
import { ChatAttachmentCard } from './ChatAttachmentCard';
import {
	AudioPlayer,
	AudioPlayerElement,
	AudioPlayerControlBar,
	AudioPlayerPlayButton,
	AudioPlayerTimeDisplay,
	AudioPlayerTimeRange,
	AudioPlayerDurationDisplay,
	AudioPlayerMuteButton,
	AudioPlayerVolumeRange,
} from '@/components/ai-elements/audio-player';
import type { LoadingType } from './ChatInput';
import { MemoryContextBadge } from '../memory/MemoryContextBadge';

const frappeUrl = import.meta.env.VITE_FRAPPE_URL || window.location.origin;

function resolveAudioSrc(src: string): string {
	if (src.startsWith('http://') || src.startsWith('https://')) return src;
	return `${frappeUrl}${src.startsWith('/') ? '' : '/'}${src}`;
}

function resolveVideoSrc(src: string): string {
	if (src.startsWith('http://') || src.startsWith('https://') || src.startsWith('data:') || src.startsWith('blob:')) return src;
	return `${frappeUrl}${src.startsWith('/') ? '' : '/'}${src}`;
}

interface ChatMessageProps {
    message: MessageType;
    /** Model name shown in the assistant action row, e.g. "gpt-4-turbo". */
    agentModel?: string;
    showToolExecutionDetails?: boolean;
    status: 'submitted' | 'streaming' | 'ready' | 'error';
    loadingType?: LoadingType;
    onFeedback: (feedback: 'Thumbs Up' | 'Thumbs Down', options?: { agentMessageId?: string; comments?: string }) => void;
    scrollToBottomAfterPaint: (instant?: boolean) => void;
    /** Content of the user turn that produced this assistant message, if known. */
    precedingUserMessage?: string;
    /** Re-runs a prior user turn (regenerate / retry). Appends a new turn rather than mutating history. */
    onRegenerate?: (userContent: string) => void;
}

export function ChatMessage({
    message,
    agentModel,
    showToolExecutionDetails = true,
    status,
    loadingType = 'default',
    onFeedback,
    scrollToBottomAfterPaint,
    precedingUserMessage,
    onRegenerate,
}: ChatMessageProps) {
    const isUser = message.from === 'user';
    const isAssistant = message.from === 'assistant';
    const isEmpty = !message.versions[0]?.content || message.versions[0].content.trim() === '';
    const runId = message.agentRunId || (
        message.key.startsWith('AR-') || message.key.startsWith('run-') ? message.key : undefined
    );

    const isBusy = status === 'submitted' || status === 'streaming';
    const handleRegenerate = precedingUserMessage && onRegenerate
        ? () => onRegenerate(precedingUserMessage)
        : undefined;

    const showLoading = isAssistant && !message.error && (
        ((status === 'submitted' || status === 'streaming') && isEmpty) ||
        message.runStatus === 'Queued' ||
        message.runStatus === 'Started'
    );

    // Skip rendering ALL tool-related messages when tool execution details are hidden
    if (!showToolExecutionDetails) {
        // Hide messages with tool-related kinds (stored in DB as text)
        const kind = message.kind;
        if (kind === 'Tool Call' || kind === 'Tool Result') {
            return null;
        }
        // Hide messages that only contain Tool UI components (from socket events)
        const hasToolsOnly = message.tools && message.tools.length > 0 &&
            (!message.versions[0]?.content || message.versions[0].content.trim() === '');
        if (hasToolsOnly) {
            return null;
        }
    }

    return (
        <div className={cn("flex flex-col group relative", isUser ? "self-end" : "self-start w-full")}>
            {showToolExecutionDetails && message.tools && message.tools.length > 0 ? (
                <div className="flex w-full max-w-chat-measure flex-col gap-2">
                    {message.tools.map((tool, toolIndex) => (
                        <Tool key={`${message.key}-tool-${toolIndex}`}>
                            <ToolHeader
                                title={tool.name}
                                type={`tool-${tool.name}` as ToolUIPart['type']}
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
                    ))}
                </div>
            ) : (
                    <Message from={message.from} className={cn(isUser && "!ml-0 max-w-[68%]", !isUser && "!max-w-full")}>
                        <MessageContent
                            className={cn(
                                isUser
                                    ? "!ml-0 !rounded-chat-bubble !bg-chat-bubble !px-3 !py-[7px] text-[13px] leading-[1.55]"
                                    : "w-full max-w-chat-measure text-[13px] leading-[1.65]"
                            )}
                        >
                            {isAssistant && message.reasoning && (
                                <Reasoning
                                    isStreaming={!!message.reasoningStreaming}
                                    defaultOpen={false}
                                    className="border-l-2 border-line pl-[9px]"
                                >
                                    <ReasoningTrigger className="text-[12px] text-steel" />
                                    <ReasoningContent>{message.reasoning}</ReasoningContent>
                                </Reasoning>
                            )}
                            {/* Show loading state while message is generating */}
                            {showLoading && (
                                <MessageLoadingState
                                    type={showToolExecutionDetails && message.tools?.length ? 'tool-execution' : loadingType}
                                    hasTools={showToolExecutionDetails && !!message.tools && message.tools.length > 0}
                                    toolName={showToolExecutionDetails ? message.tools?.[0]?.name : undefined}
                                />
                            )}
                            {message.error ? (
                                <ChatErrorCard
                                    error={message.error}
                                    onRetry={handleRegenerate}
                                    retryDisabled={isBusy}
                                />
                            ) : message.generatedAudio && message.from === 'assistant' ? (
                                <div className="w-full max-w-md">
                                    <AudioPlayer>
                                        <AudioPlayerElement src={resolveAudioSrc(message.generatedAudio)} />
                                        <AudioPlayerControlBar>
                                            <AudioPlayerPlayButton />
                                            <AudioPlayerTimeDisplay />
                                            <AudioPlayerTimeRange />
                                            <AudioPlayerDurationDisplay />
                                            <AudioPlayerMuteButton />
                                            <AudioPlayerVolumeRange />
                                        </AudioPlayerControlBar>
                                    </AudioPlayer>
                                </div>
                            ) : message.voiceMessage && message.from === 'user' ? (
                                <div className="flex flex-col gap-2 w-full max-w-md">
                                    <AudioPlayer>
                                        <AudioPlayerElement src={resolveAudioSrc(message.voiceMessage)} />
                                        <AudioPlayerControlBar>
                                            <AudioPlayerPlayButton />
                                            <AudioPlayerTimeDisplay />
                                            <AudioPlayerTimeRange />
                                            <AudioPlayerDurationDisplay />
                                            <AudioPlayerMuteButton />
                                            <AudioPlayerVolumeRange />
                                        </AudioPlayerControlBar>
                                    </AudioPlayer>
                                    {message.versions[0]?.content && (
                                        <details className="text-sm rounded-lg border border-line group [&_summary::-webkit-details-marker]:hidden">
                                            <summary className="font-medium cursor-pointer select-none p-3 hover:bg-paper-deep transition-colors rounded-lg group-open:rounded-b-none list-none flex items-center justify-between opacity-80">
                                                <span>Transcript</span>
                                                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="transition-transform group-open:rotate-180 opacity-50"><polyline points="6 9 12 15 18 9"></polyline></svg>
                                            </summary>
                                            <div className="p-3 pt-0 border-t border-line mt-2 opacity-90">
                                                <MessageContentWithArtifacts
                                                    content={message.versions[0].content}
                                                    messageId={message.versions[0]?.id ?? message.key}
                                                />
                                            </div>
                                        </details>
                                    )}
                                </div>
                            ) : message.kind === 'Image' ? (
                                <div className="flex flex-col gap-2">
                                    {message.generatedImage ? (
                                        <Image 
                                            src={message.generatedImage} 
                                            alt={message.versions[0]?.content || 'Generated image'}
                                            className="max-w-full h-auto rounded-lg border max-h-[512px] object-contain"
                                            showDownloadButton={true}
                                            onLoad={() => scrollToBottomAfterPaint(false)}
                                        />
                                    ) : (
                                        <Skeleton className="w-full h-[512px] rounded-lg" />
                                    )}
                                    {message.versions[0]?.content && (
                                        <MessageContentWithArtifacts
                                            content={message.versions[0].content}
                                            messageId={message.versions[0]?.id ?? message.key}
                                        />
                                    )}
                                </div>
                            ) : message.kind === 'Video' ? (
                                <div className="flex flex-col gap-2">
                                    {message.generatedVideo ? (
                                        <Video
                                            src={resolveVideoSrc(message.generatedVideo)}
                                            title={message.versions[0]?.content || 'Generated video'}
                                            className="max-w-full"
                                        />
                                    ) : (
                                        <Skeleton className="w-full h-[320px] rounded-lg" />
                                    )}
                                    {message.versions[0]?.content && (
                                        <MessageContentWithArtifacts
                                            content={message.versions[0].content}
                                            messageId={message.versions[0]?.id ?? message.key}
                                        />
                                    )}
                                </div>
                            ) : !message.generatedAudio && !(showLoading && !message.tools) && (
                                <>
                                    {message.attachment && (
                                        <ChatAttachmentCard
                                            name={message.attachment.name}
                                            label={message.attachment.label}
                                            previewUrl={message.attachment.previewUrl}
                                            className="mb-2 max-w-sm"
                                        />
                                    )}
                                    <MessageContentWithArtifacts
                                        content={message.versions[0]?.content || ''}
                                        messageId={message.versions[0]?.id ?? message.key}
                                    />
                                </>
                            )}
                        </MessageContent>
                        {/* Actions for assistant messages */}
                        {message.from === 'assistant' && message.versions[0]?.content && (!message.tools || !showToolExecutionDetails) && (
                            <div className="flex flex-wrap items-center gap-[14px]">
                                <MessageActions
                                    content={message.versions[0].content}
                                    onFeedback={onFeedback}
                                    agentMessageId={message.versions[0].id}
                                    agentRunId={runId}
                                    onRegenerate={handleRegenerate}
                                    regenerateDisabled={isBusy}
                                />
                                {message.injected_memories && message.injected_memories.length > 0 && (
                                    <MemoryContextBadge memoryRecordNames={message.injected_memories} />
                                )}
                                {runId && (
                                    <Link
                                        to={`/executions/${runId}`}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="inline-flex items-center gap-1 text-xs text-steel-soft hover:text-foreground transition-colors group/analytics"
                                        title="View context & cache metrics (/executions/:runId)"
                                        aria-label="View context & cache metrics"
                                    >
                                        <BarChart2 className="h-3.5 w-3.5 text-steel-soft group-hover/analytics:text-foreground" />
                                        <span className="text-[11px] font-medium">Cache metrics</span>
                                    </Link>
                                )}
                                {agentModel && (
                                    <span className="font-mono text-[11px] text-steel-soft">
                                        {agentModel}
                                    </span>
                                )}
                            </div>
                        )}
                        {/* Actions for user messages */}
                        {message.from === 'user' && message.versions[0]?.content && (
                            <div className="opacity-0 transition-opacity group-hover:opacity-100 flex items-center gap-2 text-muted-foreground">
                                <CopyButton content={message.versions[0].content} />
                                {message.injected_memories && message.injected_memories.length > 0 && (
                                    <MemoryContextBadge memoryRecordNames={message.injected_memories} />
                                )}
                            </div>
                        )}
                    </Message>
            )}
        </div>
    );
}
