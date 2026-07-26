import { AlertCircle } from "lucide-react";
import { CopyButton } from "./CopyButton";

interface ChatErrorCardProps {
    error: string;
}

/**
 * Visually distinct error state for failed agent runs — replaces the
 * assistant bubble / endless loading state when a run fails.
 */
export function ChatErrorCard({ error }: ChatErrorCardProps) {
    return (
        <div className="w-full max-w-xl rounded-lg border border-destructive/40 bg-destructive/10 p-3">
            <div className="flex items-start gap-2">
                <AlertCircle className="h-4 w-4 mt-0.5 shrink-0 text-destructive" />
                <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-destructive">Agent run failed</p>
                    <p className="text-sm text-destructive/90 whitespace-pre-wrap break-words">{error}</p>
                </div>
                <CopyButton content={error} />
            </div>
        </div>
    );
}
