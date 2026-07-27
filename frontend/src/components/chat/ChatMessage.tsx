import { Link } from 'react-router-dom';
import { BarChart2 } from 'lucide-react';
import { cn } from "@/lib/utils";
import ChatAvatar from "./ChatAvatar";
import { getInitials } from "@/utils/getInitials";
import { useUser } from "@/contexts/UserContext";
import { DEFAULT_AGENT_COLOR } from "@/data/color";
import { Message, MessageContent } from '@/components/ai-elements/message';
import { Tool, ToolHeader, ToolContent, ToolInput, ToolOutput } from '@/components/ai-elements/tool';
import type { ToolUIPart } from 'ai';
import { MessageActions } from './MessageActions';
import { MessageLoadingState } from './MessageLoadingState';
import { ChatErrorCard } from './ChatErrorCard';
import { CopyButton } from './CopyButton';
import { Image } from '@/components/ai-elements/image';
import { Video } from '@/components/ai-elements/video';
import { Skeleton } from '@/components/ui/skeleton';
import { formatTime } from './utils';
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
    agentName: string;
    agentColor: string | null;
    showToolExecutionDetails?: boolean;
    status: 'submitted' | 'streaming' | 'ready' | 'error';
    loadingType?: LoadingType;
    onFeedback: (feedback: 'Thumbs Up' | 'Thumbs Down', options?: { agentMessageId?: string; comments?: string }) => void;
    scrollToBottomAfterPaint: (instant?: boolean) => void;
}

export function ChatMessage({ 
    message, 
    agentName,
    agentColor,
    showToolExecutionDetails = true,
    status,
    loadingType = 'default',
    onFeedback,
    scrollToBottomAfterPaint,
}: ChatMessageProps) {
    const { user } = useUser();
    const isUser = message.from === 'user';
    const isAssistant = message.from === 'assistant';
    const isEmpty = !message.versions[0]?.content || message.versions[0].content.trim() === '';
    const timestamp = message.versions[0]?.id ? undefined : undefined; // We'll get timestamp from message if available
    const timeDisplay = timestamp ? formatTime(timestamp) : '';
    const userInitials = user?.full_name ? getInitials(user.full_name) : 'You';
    const runId = message.agentRunId || (
        message.key.startsWith('AR-') || message.key.startsWith('run-') ? message.key : undefined
    );

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
                    {message.injected_memories && message.injected_memories.length > 0 && (
                        <MemoryContextBadge memoryRecordNames={message.injected_memories} />
                    )}
                    {!isUser && runId && (
                        <Link
                            to={`/executions/${runId}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors ml-auto group/analytics"
                            title="View context & cache metrics (/executions/:runId)"
                            aria-label="View context & cache metrics"
                        >
                            <BarChart2 className="h-3.5 w-3.5 text-muted-foreground group-hover/analytics:text-foreground" />
                            <span className="text-[11px] font-medium">Cache metrics</span>
                        </Link>
                    )}
                </div>
                
                {showToolExecutionDetails && message.tools && message.tools.length > 0 ? (
                    message.tools.map((tool, toolIndex) => (
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
                    ))
                ) : (
                    <Message from={message.from} className={cn(isUser && "!ml-0", !isUser && "!max-w-full")}>
                        <MessageContent className={cn(isUser && "!ml-0", !isUser && "w-full")}>
                            {/* Show loading state while message is generating */}
                            {showLoading && (
                                <MessageLoadingState
                                    type={showToolExecutionDetails && message.tools?.length ? 'tool-execution' : loadingType}
                                    hasTools={showToolExecutionDetails && !!message.tools && message.tools.length > 0}
                                    toolName={showToolExecutionDetails ? message.tools?.[0]?.name : undefined}
                                />
                            )}
                            {message.error ? (
                                <ChatErrorCard error={message.error} />
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
                                        <details className="text-sm rounded-lg border border-black/10 dark:border-white/10 group [&_summary::-webkit-details-marker]:hidden">
                                            <summary className="font-medium cursor-pointer select-none p-3 hover:bg-black/5 dark:hover:bg-white/5 transition-colors rounded-lg group-open:rounded-b-none list-none flex items-center justify-between opacity-80">
                                                <span>Transcript</span>
                                                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="transition-transform group-open:rotate-180 opacity-50"><polyline points="6 9 12 15 18 9"></polyline></svg>
                                            </summary>
                                            <div className="p-3 pt-0 border-t border-black/10 dark:border-white/10 mt-2 opacity-90">
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
                            <div className="opacity-0 transition-opacity group-hover:opacity-100">
                                <MessageActions
                                    content={message.versions[0].content}
                                    onFeedback={onFeedback}
                                    agentMessageId={message.versions[0].id}
                                    agentRunId={runId}
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
