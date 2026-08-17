import { AlertCircle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { CopyButton } from "./CopyButton";

interface ChatErrorCardProps {
    error: string;
    /** Re-attempts the user turn that failed. Omitted when the source turn is unknown. */
    onRetry?: () => void;
    /** True while a turn is already in flight, to prevent overlapping runs. */
    retryDisabled?: boolean;
}

/**
 * Visually distinct error state for failed agent runs — replaces the
 * assistant bubble / endless loading state when a run fails.
 */
export function ChatErrorCard({ error, onRetry, retryDisabled }: ChatErrorCardProps) {
    return (
        <div className="w-full max-w-xl rounded-lg border border-destructive/40 bg-destructive/10 p-3">
            <div className="flex items-start gap-2">
                <AlertCircle className="h-4 w-4 mt-0.5 shrink-0 text-destructive" />
                <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-destructive">Agent run failed</p>
                    <p className="text-sm text-destructive/90 whitespace-pre-wrap break-words">{error}</p>
                    {onRetry && (
                        <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            className="mt-2 h-7 gap-1.5 text-xs"
                            onClick={onRetry}
                            disabled={retryDisabled}
                        >
                            <RefreshCw className="h-3.5 w-3.5" />
                            Retry
                        </Button>
                    )}
                </div>
                <CopyButton content={error} />
            </div>
        </div>
    );
}
