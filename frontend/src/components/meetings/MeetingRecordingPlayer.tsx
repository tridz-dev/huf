import { useMemo, useState } from 'react';
import { AlertTriangle, Captions, Music } from 'lucide-react';
import {
  AudioPlayer,
  AudioPlayerControlBar,
  AudioPlayerDurationDisplay,
  AudioPlayerElement,
  AudioPlayerMuteButton,
  AudioPlayerPlayButton,
  AudioPlayerTimeDisplay,
  AudioPlayerTimeRange,
} from '@/components/ai-elements/audio-player';
import { formatElapsed } from '@/components/meetings/MeetingTranscriptPanel';
import { cn } from '@/lib/utils';
import type { MeetingRecordingChunk } from '@/types/meeting.types';

interface MeetingRecordingPlayerProps {
  chunks: MeetingRecordingChunk[];
}

// Mirrors the FrappeApp base URL resolution in lib/frappe-sdk.ts — `Attach`
// field values on Meeting Recording Chunk are site-relative paths
// (/private/files/...), same-origin cookie auth applies, so this just needs
// the same origin frappe-sdk calls resolve against, not a new auth path.
const FRAPPE_URL = import.meta.env.VITE_FRAPPE_URL || window.location.origin;

function resolveFileUrl(audioFile: string): string {
  if (/^https?:\/\//.test(audioFile)) return audioFile;
  return `${FRAPPE_URL}${audioFile.startsWith('/') ? '' : '/'}${audioFile}`;
}

/**
 * Sequential multi-chunk playback. There is no combined-recording file on
 * the backend (PLAN.md D.4), so this plays each chunk's `audio_file` in
 * `sequence` order via a single `<audio>` element, advancing on `ended`.
 */
export function MeetingRecordingPlayer({ chunks }: MeetingRecordingPlayerProps) {
  const playableChunks = useMemo(
    () =>
      chunks
        .slice()
        .sort((a, b) => a.sequence - b.sequence)
        .filter((chunk) => !!chunk.audio_file),
    [chunks],
  );
  const [currentIndex, setCurrentIndex] = useState(0);
  const [showCaptions, setShowCaptions] = useState(true);

  // Running elapsed offset up to (not including) the current chunk, same
  // fallback logic as MeetingTranscriptPanel: prefer client_started_at,
  // else accumulate prior chunks' durations.
  const currentElapsedSeconds = useMemo(() => {
    let runningSeconds = 0;
    for (let i = 0; i < playableChunks.length; i += 1) {
      const chunk = playableChunks[i];
      const timestampSeconds = chunk.client_started_at
        ? Number(chunk.client_started_at) || runningSeconds
        : runningSeconds;
      if (i === Math.min(currentIndex, playableChunks.length - 1)) {
        return timestampSeconds;
      }
      runningSeconds = timestampSeconds + (chunk.duration_seconds || 0);
    }
    return runningSeconds;
  }, [playableChunks, currentIndex]);

  if (playableChunks.length === 0) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-dashed border-line px-4 py-3 text-sm text-steel">
        <Music className="h-4 w-4 text-steel-soft" aria-hidden />
        No recording available for this meeting.
      </div>
    );
  }

  const current = playableChunks[Math.min(currentIndex, playableChunks.length - 1)];
  const isLastChunk = currentIndex >= playableChunks.length - 1;
  const isGap = current.upload_status === 'Failed' || !!current.transcription_error;

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center gap-2">
        <AudioPlayer key={current.name} className="flex-1">
          <AudioPlayerElement
            src={resolveFileUrl(current.audio_file!)}
            onEnded={() => {
              if (!isLastChunk) {
                setCurrentIndex((index) => index + 1);
              }
            }}
          />
          <AudioPlayerControlBar>
            <AudioPlayerPlayButton />
            <AudioPlayerTimeDisplay />
            <AudioPlayerTimeRange />
            <AudioPlayerDurationDisplay />
            <AudioPlayerMuteButton />
          </AudioPlayerControlBar>
        </AudioPlayer>
        <button
          type="button"
          onClick={() => setShowCaptions((value) => !value)}
          aria-pressed={showCaptions}
          aria-label={showCaptions ? 'Hide captions' : 'Show captions'}
          title={showCaptions ? 'Hide captions' : 'Show captions'}
          className={cn(
            'shrink-0 rounded-md p-1.5 text-steel-soft transition-colors hover:bg-canvas-soft hover:text-ink',
            showCaptions && 'text-ink',
          )}
        >
          <Captions className="h-4 w-4" aria-hidden />
        </button>
      </div>
      {showCaptions && (
        <div className="flex items-start gap-2 rounded-md bg-ink/85 px-4 py-2 text-center">
          <span className="mt-0.5 shrink-0 font-mono text-xs tabular-nums text-white/70" aria-hidden>
            {formatElapsed(currentElapsedSeconds)}
          </span>
          {isGap ? (
            <p className="flex-1 flex items-center justify-center gap-1.5 text-sm italic text-white/90">
              <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-amber-400" aria-hidden />
              {current.transcript_text || '[this part could not be transcribed]'}
            </p>
          ) : (
            <p className="flex-1 text-center text-sm text-white">
              {current.transcript_text || '[this part could not be transcribed]'}
            </p>
          )}
        </div>
      )}
      {playableChunks.length > 1 && (
        <span className="font-body text-xs text-steel-soft">
          Part {currentIndex + 1} of {playableChunks.length}
        </span>
      )}
    </div>
  );
}
