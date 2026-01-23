import { Shimmer } from "@/components/ai-elements/shimmer";
import { cn } from "@/lib/utils";

type MessageLoadingStateProps = {
  hasTools?: boolean;
  toolName?: string;
  className?: string;
};

export function MessageLoadingState({
  hasTools = false,
  toolName,
  className,
}: MessageLoadingStateProps) {
  // Determine the loading message based on context
  const loadingMessage = hasTools
    ? toolName
      ? `Executing ${toolName}...`
      : "Executing Tool..."
    : "Thinking...";

  return (
    <div
      className={cn(
        "flex items-center gap-2 w-full max-w-md min-h-[60px] py-2",
        className
      )}
    >
      <Shimmer className="text-sm text-muted-foreground">
        {loadingMessage}
      </Shimmer>
    </div>
  );
}
