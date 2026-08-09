import { useEffect, useState } from 'react';
import {
	Collapsible,
	CollapsibleContent,
	CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { Tool, ToolHeader, ToolContent, ToolInput, ToolOutput } from '@/components/ai-elements/tool';
import type { ToolUIPart } from 'ai';
import {
	CheckCircleIcon,
	ChevronDownIcon,
	ClockIcon,
	WrenchIcon,
	XCircleIcon,
} from 'lucide-react';
import type { MessageType } from './types';

type ToolCallGroupProps = {
	messageKey: string;
	tools: NonNullable<MessageType['tools']>;
	runStatus?: MessageType['runStatus'];
	/** Groups hydrated from conversation history have no "in-flight" signal — render collapsed. */
	isHistorical?: boolean;
};

function aggregateState(tools: ToolCallGroupProps['tools']): 'running' | 'error' | 'done' {
	if (tools.some((t) => t.status === 'output-error')) return 'error';
	if (tools.some((t) => t.status !== 'output-available' && t.status !== 'output-error')) return 'running';
	return 'done';
}

const AGGREGATE_ICON: Record<ReturnType<typeof aggregateState>, React.ReactNode> = {
	running: <ClockIcon className="size-4 animate-pulse text-muted-foreground" />,
	done: <CheckCircleIcon className="size-4 text-green-600" />,
	error: <XCircleIcon className="size-4 text-red-600" />,
};

const AGGREGATE_LABEL: Record<ReturnType<typeof aggregateState>, string> = {
	running: 'Running',
	done: 'Completed',
	error: 'Error',
};

/**
 * Collapsible group for every tool call within one assistant turn/run,
 * replacing a flat stack of individually-full-width Tool cards with a
 * single summary row the user can expand. Auto-expands while the run is
 * in flight (so the user can watch it work) and auto-collapses once it
 * completes; historical (reloaded) groups start collapsed since there's
 * no in-flight signal for them.
 */
export function ToolCallGroup({ messageKey, tools, runStatus, isHistorical }: ToolCallGroupProps) {
	const isRunning = runStatus === 'Queued' || runStatus === 'Started';
	const [open, setOpen] = useState(!isHistorical && isRunning);
	const [userToggled, setUserToggled] = useState(false);

	// Auto-collapse when the run finishes, unless the user already interacted with the group.
	useEffect(() => {
		if (!isRunning && !userToggled) setOpen(false);
	}, [isRunning, userToggled]);

	if (tools.length === 0) return null;

	const state = aggregateState(tools);
	const summary = tools.length === 1
		? tools[0].name
		: tools.map((t) => t.name).join(' → ');

	return (
		<Collapsible
			open={open}
			onOpenChange={(next) => {
				setUserToggled(true);
				setOpen(next);
			}}
			className="not-prose mb-4 w-full rounded-md border"
		>
			<CollapsibleTrigger className="flex w-full items-center justify-between gap-4 p-3">
				<div className="flex min-w-0 items-center gap-2">
					<WrenchIcon className="size-4 shrink-0 text-muted-foreground" />
					<span className="truncate font-medium text-sm">
						{tools.length > 1 ? `Ran ${tools.length} tools` : summary}
					</span>
					{tools.length > 1 && (
						<span className="truncate text-muted-foreground text-xs">{summary}</span>
					)}
					<Badge className="shrink-0 gap-1.5 rounded-full text-xs" variant="secondary">
						{AGGREGATE_ICON[state]}
						{AGGREGATE_LABEL[state]}
					</Badge>
				</div>
				<ChevronDownIcon className={cn('size-4 shrink-0 text-muted-foreground transition-transform', open && 'rotate-180')} />
			</CollapsibleTrigger>
			<CollapsibleContent className="space-y-2 border-t p-2">
				{tools.map((tool, toolIndex) => (
					<Tool key={`${messageKey}-tool-${tool.tool_call_id || toolIndex}`}>
						<ToolHeader
							title={tool.name}
							type={`tool-${tool.name}` as ToolUIPart['type']}
							state={tool.status}
						/>
						<ToolContent>
							<ToolInput input={tool.parameters} />
							<ToolOutput output={tool.result} errorText={tool.error} />
						</ToolContent>
					</Tool>
				))}
			</CollapsibleContent>
		</Collapsible>
	);
}
