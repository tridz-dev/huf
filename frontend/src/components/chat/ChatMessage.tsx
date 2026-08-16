import { Link } from 'react-router-dom';
import { BarChart2, BrainIcon, ChevronDownIcon } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from "@/lib/utils";
import { Message, MessageContent } from '@/components/ai-elements/message';
import { Tool, ToolHeader, ToolContent, ToolInput, ToolOutput, ToolGroup } from '@/components/ai-elements/tool';
import { Reasoning, ReasoningTrigger, ReasoningContent } from '@/components/ai-elements/reasoning';
import { Shimmer } from '@/components/ai-elements/shimmer';
import type { ToolUIPart } from 'ai';
import { HubAskUser, splitAskUserBlocks } from '../hub/HubAskUser';
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
    /** Sends text as a new user message — wired to the ask-user "answer" buttons. */
    onSendText?: (text: string) => void;
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
    onSendText,
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

    // TODO(tool-call-approval-api): there is no backend/socket endpoint yet to
    // approve or deny a pending tool call (only flow-run-level approvals exist,
    // see ApprovalsBell.tsx / flowApi.ts). These are UI-only stubs so the
    // "approval-requested" state is visually complete; wire them to a real
    // call/agent-run approve-deny endpoint once one exists.
    const handleToolCallApprove = (toolCallId: string) => {
        console.warn('tool-call approval API not yet implemented', { toolCallId });
        toast.info("Approving tool calls isn't wired up yet.");
    };

    const handleToolCallDeny = (toolCallId: string) => {
        console.warn('tool-call approval API not yet implemented', { toolCallId });
        toast.info("Denying tool calls isn't wired up yet.");
    };

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
        <div className="flex flex-col group relative w-full">
            {showToolExecutionDetails && message.tools && message.tools.length > 0 ? (
                <div className="flex w-full max-w-chat-measure flex-col gap-2">
                    {message.tools.length > 1 ? (
                        <ToolGroup
                            calls={message.tools.map((tool) => ({
                                callId: tool.tool_call_id,
                                name: tool.name,
                                state: tool.status,
                                input: tool.parameters,
                                output: tool.result,
                                errorText: tool.error,
                                durationMs: tool.durationMs,
                            }))}
                            runStatus={message.runStatus}
                            isHistorical={!message.runStatus}
                            onApprove={handleToolCallApprove}
                            onDeny={handleToolCallDeny}
                        />
                    ) : (
                        <Tool key={`${message.key}-tool-0`}>
                            <ToolHeader
                                title={message.tools[0].name}
                                type={`tool-${message.tools[0].name}` as ToolUIPart['type']}
                                state={message.tools[0].status}
                                durationMs={message.tools[0].durationMs}
                                onRetry={handleRegenerate}
                                onApprove={() => handleToolCallApprove(message.tools![0].tool_call_id)}
                                onDeny={() => handleToolCallDeny(message.tools![0].tool_call_id)}
                            />
                            <ToolContent>
                                <ToolInput input={message.tools[0].parameters} />
                                <ToolOutput
                                    output={message.tools[0].result}
                                    errorText={message.tools[0].error}
                                />
                            </ToolContent>
                        </Tool>
                    )}
                </div>
            ) : (
                    <Message from={message.from} className={cn(isUser && "max-w-[68%]", !isUser && "!max-w-full")}>
                        <MessageContent
                            className={cn(
                                isUser
                                    ? "!rounded-chat-bubble !bg-chat-bubble !px-3 !py-[7px] text-[13px] leading-[1.55]"
                                    : "w-full max-w-chat-measure text-[13px] leading-[1.65]"
                            )}
                        >
                            {isAssistant && message.reasoning && (
                                <Reasoning
                                    isStreaming={!!message.reasoningStreaming}
                                    defaultOpen={false}
                                    className="border-l-2 border-line pl-[9px]"
                                >
                                    <ReasoningTrigger className="gap-[7px] text-[12px] text-steel data-[state=open]:[&_.reasoning-chevron]:rotate-180">
                                        <BrainIcon className="size-[14px]" />
                                        {message.reasoningStreaming ? (
                                            <Shimmer duration={1}>Thinking...</Shimmer>
                                        ) : (
                                            <p>Thought for a few seconds</p>
                                        )}
                                        <ChevronDownIcon className="reasoning-chevron size-[13px] transition-transform" />
                                    </ReasoningTrigger>
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
                                    {isAssistant ? (() => {
                                        // Extract fenced ```ask-user blocks (from the ask_user tool) so any
                                        // agent with it attached renders the interactive question widget,
                                        // not raw fenced markdown — same parsing HubConversationView uses.
                                        const { text, blocks } = splitAskUserBlocks(message.versions[0]?.content || '');
                                        return (
                                            <>
                                                {text && (
                                                    <MessageContentWithArtifacts
                                                        content={text}
                                                        messageId={message.versions[0]?.id ?? message.key}
                                                    />
                                                )}
                                                {blocks.map((block, blockIndex) => (
                                                    <HubAskUser
                                                        key={`${message.key}-ask-${blockIndex}`}
                                                        payload={block}
                                                        onSubmit={(answer) =>
                                                            onSendText?.(`Regarding "${block.question}": ${answer}`)
                                                        }
                                                    />
                                                ))}
                                            </>
                                        );
                                    })() : (
                                        <MessageContentWithArtifacts
                                            content={message.versions[0]?.content || ''}
                                            messageId={message.versions[0]?.id ?? message.key}
                                        />
                                    )}
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
