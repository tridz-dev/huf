import { Shimmer } from "@/components/ai-elements/shimmer";
import { cn } from "@/lib/utils";
import { BrainCircuit, Cog, Mic } from "lucide-react";
import { useEffect, useState } from "react";

import loadingMessages from "@/data/loading-messages.json";

export type LoadingType = "default" | "tool-execution" | "transcribing";

type MessageLoadingStateProps = {
	type?: LoadingType;
	hasTools?: boolean;
	toolName?: string;
	className?: string;
};

const TYPE_ICONS = {
	default: BrainCircuit,
	"tool-execution": Cog,
	transcribing: Mic,
} as const;

export function MessageLoadingState({
	type = "default",
	hasTools = false,
	toolName,
	className,
}: MessageLoadingStateProps) {
	// Tool name override: static message, no cycling
	const toolOverride = hasTools && toolName ? `Executing ${toolName}...` : hasTools ? "Executing Tool..." : null;

	const messages = toolOverride
		? [toolOverride]
		: (loadingMessages as Record<LoadingType, string[]>)[type] ?? loadingMessages.default;

	const [index, setIndex] = useState(() => Math.floor(Math.random() * messages.length));
	const displayMessage = messages[index % messages.length];
	const Icon = toolOverride ? TYPE_ICONS["tool-execution"] : TYPE_ICONS[type];

	useEffect(() => {
		if (messages.length <= 1) return;
		const interval = setInterval(() => {
			setIndex((i) => (i + 1) % messages.length);
		}, 3000);
		return () => clearInterval(interval);
	}, [messages.length]);

	return (
		<div
			className={cn(
				"flex items-center gap-2 w-full max-w-md min-h-[60px] py-2",
				className
			)}
		>
			<Icon className="size-4 shrink-0 text-muted-foreground" />
			<Shimmer className="text-sm text-muted-foreground">
				{displayMessage}
			</Shimmer>
		</div>
	);
}
