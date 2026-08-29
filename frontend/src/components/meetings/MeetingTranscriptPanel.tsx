import { useEffect, useRef } from 'react';
import { AlertTriangle, FileText } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { MeetingRecordingChunk } from '@/types/meeting.types';

interface MeetingTranscriptPanelProps {
  chunks: MeetingRecordingChunk[];
  /** Whether the meeting is still being transcribed — enables auto-scroll. */
  isLive?: boolean;
  className?: string;
}

/** `mm:ss` (or `h:mm:ss` past an hour) elapsed-from-start timestamp for a chunk. */
export function formatElapsed(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const mm = h > 0 ? String(m).padStart(2, '0') : String(m);
  const ss = String(s).padStart(2, '0');
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

/**
 * Timestamped transcript, one paragraph per chunk boundary (PLAN.md G.1
 * "transcript readability"). Auto-scrolls to the newest chunk while the
 * meeting is still transcribing; becomes a static scrollable/searchable
 * (browser find-in-page) panel once complete. Failed chunks already carry
 * the backend's inline "[this part could not be transcribed]" text
 * (Phase 4) — this renders that text as-is and adds a visible gap marker
 * treatment, it does not invent new placeholder copy.
 */
export function MeetingTranscriptPanel({ chunks, isLive, className }: MeetingTranscriptPanelProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const transcribedChunks = chunks
    .slice()
    .sort((a, b) => a.sequence - b.sequence)
    .filter((chunk) => !!chunk.transcript_text || chunk.upload_status === 'Failed');

  useEffect(() => {
    if (isLive) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
  }, [isLive, chunks.length]);

  if (transcribedChunks.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-line py-10 text-center">
        <FileText className="h-5 w-5 text-steel-soft" aria-hidden />
        <p className="font-body text-sm text-steel">Meeting has no transcript yet.</p>
      </div>
    );
  }

  // Running elapsed offset, computed from each chunk's own duration since
  // client_started_at isn't guaranteed to be populated for every chunk.
  let runningSeconds = 0;

  return (
    <div
      className={cn('flex max-h-[60vh] flex-col gap-4 overflow-y-auto rounded-lg border border-line p-4', className)}
      role="log"
      aria-label="Meeting transcript"
    >
      {transcribedChunks.map((chunk) => {
        const timestampSeconds = chunk.client_started_at
          ? Number(chunk.client_started_at) || runningSeconds
          : runningSeconds;
        runningSeconds = timestampSeconds + (chunk.duration_seconds || 0);
        const isGap = chunk.upload_status === 'Failed' || !!chunk.transcription_error;

        return (
          <div key={chunk.name} className="flex gap-3">
            <span
              className="mt-0.5 shrink-0 font-mono text-xs tabular-nums text-steel-soft"
              aria-hidden
            >
              {formatElapsed(timestampSeconds)}
            </span>
            {isGap ? (
              <p className="flex items-start gap-1.5 text-sm leading-7 text-steel italic">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" aria-hidden />
                {chunk.transcript_text || '[this part could not be transcribed]'}
              </p>
            ) : (
              <p className="text-sm leading-7 text-ink">{chunk.transcript_text}</p>
            )}
          </div>
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
}
