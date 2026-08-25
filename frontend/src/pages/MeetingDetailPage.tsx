import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { AlertTriangle, Calendar, Clock, FileDown, Users } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { MeetingChatPanel } from '@/components/meetings/MeetingChatPanel';
import { MeetingFailureCard } from '@/components/meetings/MeetingFailureCard';
import { MeetingProcessingStatus } from '@/components/meetings/MeetingProcessingStatus';
import { MeetingSummaryPanel } from '@/components/meetings/MeetingSummaryPanel';
import { MeetingTranscriptPanel } from '@/components/meetings/MeetingTranscriptPanel';
import { MeetingRecordingPlayer } from '@/components/meetings/MeetingRecordingPlayer';
import { PostMeetingContextPanel } from '@/components/meetings/PostMeetingContextPanel';
import { useMeetingProcessingSocket } from '@/hooks/useMeetingProcessingSocket';
import { getMeeting, retryChunkTranscription, retrySummary } from '@/services/meetingApi';
import { downloadMeetingMinutes, downloadMeetingTranscript } from '@/services/meetingExport';
import { formatTimeAgo } from '@/utils/time';
import type { GetMeetingResult } from '@/services/meetingApi';

function formatDuration(seconds?: number): string {
  if (!seconds || seconds <= 0) return '—';
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const remaining = minutes % 60;
  return remaining > 0 ? `${hours}h ${remaining}m` : `${hours}h`;
}

/**
 * Meeting Detail — renders by `meeting.status` per PLAN.md G.1:
 *  - Transcribing/Summarizing: progress + whatever transcript is already
 *    available (progressive display), driven live by the
 *    `meeting_processing_status` socket event.
 *  - Completed: Summary above Transcript (most users want the summary
 *    first), recording playback + compact metadata header.
 *  - Failed: a distinct error state with a Retry action, not confused with
 *    "no transcript yet".
 */
export { MeetingDetailPage };
export default MeetingDetailPage;

function MeetingDetailPage() {
  const { meetingId } = useParams<{ meetingId: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<GetMeetingResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [contextDismissed, setContextDismissed] = useState(false);
  const lastLiveSignatureRef = useRef<string | null>(null);

  const { status: liveStatus, chunksTranscribed } = useMeetingProcessingSocket(meetingId ?? null);

  const load = useCallback(async () => {
    if (!meetingId) return;
    try {
      const result = await getMeeting(meetingId);
      setData(result);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Failed to load meeting'));
    } finally {
      setLoading(false);
    }
  }, [meetingId]);

  useEffect(() => {
    setLoading(true);
    load();
  }, [load]);

  // Re-fetch the full meeting (transcript/summary/chunks) whenever the
  // realtime processing status advances or a new chunk finishes
  // transcribing — the socket event only carries counts, not the updated
  // document, so progressive display needs this refetch to show anything.
  useEffect(() => {
    if (!liveStatus) return;
    const signature = `${liveStatus}:${chunksTranscribed}`;
    if (lastLiveSignatureRef.current === signature) return;
    lastLiveSignatureRef.current = signature;
    load();
  }, [liveStatus, chunksTranscribed, load]);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="font-body text-steel-soft">Loading meeting...</div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
        <AlertTriangle className="h-6 w-6 text-destructive" aria-hidden />
        <p className="font-body text-sm text-ink">Couldn't load this meeting.</p>
        <p className="font-body text-xs text-steel">{error?.message}</p>
        <Button variant="outline" size="sm" onClick={() => { setLoading(true); load(); }}>
          Try again
        </Button>
      </div>
    );
  }

  const { meeting, chunks } = data;
  const status = liveStatus ?? meeting.status;
  const failedChunks = chunks.filter((chunk) => chunk.upload_status === 'Failed');
  const hasTranscriptButNoSummary = !!meeting.transcript && !meeting.summary;

  const handleRetry = async () => {
    setRetrying(true);
    try {
      if (failedChunks.length > 0) {
        await Promise.all(failedChunks.map((chunk) => retryChunkTranscription(chunk.name)));
        toast.success('Retrying transcription for the failed segment(s)');
      } else if (hasTranscriptButNoSummary || meeting.transcript) {
        await retrySummary(meeting.name);
        toast.success('Retrying summary generation');
      } else {
        toast.error('Nothing to retry — no transcript is available for this meeting.');
        return;
      }
      await load();
    } catch (err) {
      toast.error('Retry failed', {
        description: err instanceof Error ? err.message : 'An unexpected error occurred.',
      });
    } finally {
      setRetrying(false);
    }
  };

  const showContextPanel = !meeting.context_completed && !contextDismissed && status !== 'Recording' && status !== 'Paused';

  const header = (
    <div className="flex flex-col gap-2">
      <h1 className="font-heading text-xl font-medium text-ink">
        {meeting.title?.trim() || `Meeting — ${formatTimeAgo(meeting.started_at || meeting.creation)}`}
      </h1>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 font-body text-xs text-steel">
        <span className="flex items-center gap-1">
          <Calendar className="h-3.5 w-3.5" aria-hidden />
          {formatTimeAgo(meeting.started_at || meeting.creation)}
        </span>
        <span className="flex items-center gap-1">
          <Clock className="h-3.5 w-3.5" aria-hidden />
          {formatDuration(meeting.duration_seconds)}
        </span>
        {meeting.participants && (
          <span className="flex items-center gap-1">
            <Users className="h-3.5 w-3.5" aria-hidden />
            {meeting.participants}
          </span>
        )}
      </div>
      {meeting.description && <p className="font-body text-sm text-steel">{meeting.description}</p>}
    </div>
  );

  return (
    <div className="h-full overflow-auto">
      <div className="mx-auto flex max-w-3xl flex-col gap-6 p-6">
        {header}

        {showContextPanel && (
          <PostMeetingContextPanel
            meetingName={meeting.name}
            onDismiss={() => setContextDismissed(true)}
            onSaved={() => load()}
          />
        )}

        {(status === 'Transcribing' || status === 'Summarizing') && (
          <div className="rounded-lg border border-line bg-card p-4">
            <MeetingProcessingStatus meetingName={meeting.name} initialStatus={status} />
          </div>
        )}

        {status === 'Stopped' && (
          <div className="rounded-lg border border-line bg-card p-4 font-body text-sm text-steel">
            Starting to process your recording...
          </div>
        )}

        {status === 'Failed' && (
          <MeetingFailureCard
            failedStep={meeting.failed_step}
            lastError={meeting.last_error}
            errorLog={meeting.error_log}
            onRetry={handleRetry}
            retrying={retrying}
          />
        )}

        {status === 'Completed' && chunks.some((chunk) => !!chunk.audio_file) && (
          <MeetingRecordingPlayer chunks={chunks} />
        )}

        {status === 'Completed' && (
          <>
            <div>
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <h2 className="font-body text-sm font-medium text-ink">Summary</h2>
                <div className="flex items-center gap-1">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => downloadMeetingTranscript(meeting.name)}
                  >
                    <FileDown className="h-3.5 w-3.5" aria-hidden />
                    Download transcript
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => downloadMeetingMinutes(meeting.name)}
                  >
                    <FileDown className="h-3.5 w-3.5" aria-hidden />
                    Download minutes
                  </Button>
                  <Button
                    variant="link"
                    size="sm"
                    className="h-auto p-0 text-xs"
                    onClick={() => document.getElementById('transcript')?.scrollIntoView({ behavior: 'smooth' })}
                  >
                    Jump to transcript
                  </Button>
                </div>
              </div>
              <MeetingSummaryPanel summary={meeting.summary} />
            </div>

            <Separator />

            <div id="transcript">
              <h2 className="mb-3 font-body text-sm font-medium text-ink">Transcript</h2>
              <MeetingTranscriptPanel chunks={chunks} isLive={false} />
            </div>

            <MeetingChatPanel
              meetingName={meeting.name}
              hasTranscript={!!meeting.transcript}
              hasSummary={!!meeting.summary}
              onSummaryRevised={load}
            />
          </>
        )}

        {(status === 'Transcribing' || status === 'Summarizing') && (
          <div>
            <h2 className="mb-3 font-body text-sm font-medium text-ink">Transcript so far</h2>
            <MeetingTranscriptPanel chunks={chunks} isLive={status === 'Transcribing'} />
          </div>
        )}

        {status === 'Failed' && meeting.transcript && (
          <div>
            <h2 className="mb-3 font-body text-sm font-medium text-ink">Transcript</h2>
            <MeetingTranscriptPanel chunks={chunks} isLive={false} />
          </div>
        )}

        <div>
          <Button variant="link" size="sm" className="h-auto p-0" onClick={() => navigate('/meetings')}>
            Back to meetings
          </Button>
        </div>
      </div>
    </div>
  );
}
