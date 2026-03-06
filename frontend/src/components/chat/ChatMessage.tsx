import { cn } from "@/lib/utils";
import ChatAvatar from "./ChatAvatar";
import { getInitials } from "@/utils/getInitials";
import { useUser } from "@/contexts/UserContext";
import { DEFAULT_AGENT_COLOR } from "@/data/color";
import { Message, MessageContent } from '@/components/ai-elements/message';
import { Tool, ToolHeader, ToolContent, ToolInput, ToolOutput } from '@/components/ai-elements/tool';
import { MessageActions } from './MessageActions';
import { MessageLoadingState } from './MessageLoadingState';
import { CopyButton } from './CopyButton';
import { Image } from '@/components/ai-elements/image';
import { Skeleton } from '@/components/ui/skeleton';
import { formatTime } from './utils';
import type { MessageType } from './types';
import { MessageContentWithArtifacts } from './MessageContentWithArtifacts';
import {
    AudioPlayer,
    AudioPlayerElement,
    AudioPlayerControlBar,
    AudioPlayerPlayButton,
    AudioPlayerTimeDisplay,
    AudioPlayerTimeRange,
    AudioPlayerDurationDisplay,
    AudioPlayerMuteButton
} from '@/components/ai-elements/audio-player';

interface ChatMessageProps {
    message: MessageType;
    agentName: string;
    agentColor: string | null;
    status: 'submitted' | 'streaming' | 'ready' | 'error';
    onFeedback: (feedback: 'Thumbs Up' | 'Thumbs Down', options?: { agentMessageId?: string; comments?: string }) => void;
    scrollToBottomAfterPaint: (instant?: boolean) => void;
}

export function ChatMessage({
    message,
    agentName,
    agentColor,
    status,
    onFeedback,
    scrollToBottomAfterPaint,
}: ChatMessageProps) {
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
                    <Message from={message.from} className={cn(isUser && "!ml-0", !isUser && "!max-w-full")}>
                        <MessageContent className={cn(isUser && "!ml-0", !isUser && "w-full")}>
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
                                            onLoad={() => scrollToBottomAfterPaint(false)}
                                        />
                                    ) : (
                                        <Skeleton className="w-full h-[512px] rounded-lg" />
                                    )}
                                    {message.versions[0]?.content && (
                                        <MessageContentWithArtifacts
                                            content={message.versions[0].content}
                                            messageKey={message.key}
                                        />
                                    )}
                                </div>
                            ) : message.kind === 'Audio' ? (
                                <div className="flex flex-col gap-2">
                                    <AudioPlayer>
                                        <AudioPlayerElement
                                            src={message.generatedAudioMp3 || message.voiceMessage || message.generatedAudio || ''}
                                            autoPlay={false}
                                        />
                                        <AudioPlayerControlBar>
                                            <AudioPlayerPlayButton />
                                            <AudioPlayerTimeDisplay />
                                            <AudioPlayerTimeRange />
                                            <AudioPlayerDurationDisplay />
                                            <AudioPlayerMuteButton />
                                        </AudioPlayerControlBar>
                                    </AudioPlayer>
                                    {message.versions[0]?.content && (
                                        <MessageContentWithArtifacts
                                            content={message.versions[0].content}
                                            messageKey={message.key}
                                        />
                                    )}
                                </div>
                            ) : !((status === 'submitted' || status === 'streaming') &&
                                message.from === 'assistant' &&
                                (!message.versions[0]?.content || message.versions[0].content.trim() === '') &&
                                !message.tools) && (
                                <MessageContentWithArtifacts
                                    content={message.versions[0]?.content || ''}
                                    messageKey={message.key}
                                />
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
