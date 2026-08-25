import { CheckCircle2, Loader2, XCircle } from 'lucide-react';
import { Progress } from '@/components/ui/progress';
import { useMeetingProcessingSocket } from '@/hooks/useMeetingProcessingSocket';

interface MeetingProcessingStatusProps {
    meetingName: string;
    /** Server-side status at mount, before any realtime event has landed. */
    initialStatus?: 'Transcribing' | 'Summarizing' | 'Completed' | 'Failed';
}

/**
 * Two-stage processing progress ("Transcribing N/M" -> "Summarizing"), driven
 * by the `meeting_processing_status` realtime event (see
 * `useMeetingProcessingSocket`). Per PLAN.md G.1, this is determinate
 * wherever the server can tell us chunk counts rather than a bare spinner.
 */
export function MeetingProcessingStatus({ meetingName, initialStatus }: MeetingProcessingStatusProps) {
    const { status, chunksTranscribed, chunksTotal } = useMeetingProcessingSocket(meetingName);
    const currentStatus = status ?? initialStatus ?? null;

    if (!currentStatus || currentStatus === 'Completed') {
        return null;
    }

    if (currentStatus === 'Failed') {
        return (
            <div className="flex items-center gap-2 text-sm text-destructive">
                <XCircle className="h-4 w-4" aria-hidden />
                <span>Processing failed</span>
            </div>
        );
    }

    if (currentStatus === 'Summarizing') {
        return (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                <span>Summarizing</span>
            </div>
        );
    }

    // Transcribing: determinate progress once we know the total chunk count,
    // otherwise fall back to an indeterminate label.
    const hasCounts = chunksTotal > 0;
    const percent = hasCounts ? Math.round((chunksTranscribed / chunksTotal) * 100) : 0;

    return (
        <div className="flex flex-col gap-1.5 text-sm text-muted-foreground">
            <div className="flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                <span>
                    {hasCounts
                        ? `Transcribing ${chunksTranscribed}/${chunksTotal}`
                        : 'Transcribing'}
                </span>
                {hasCounts && chunksTranscribed === chunksTotal && (
                    <CheckCircle2 className="h-4 w-4 text-primary" aria-hidden />
                )}
            </div>
            {hasCounts && <Progress value={percent} className="h-1.5 w-48" />}
        </div>
    );
}
