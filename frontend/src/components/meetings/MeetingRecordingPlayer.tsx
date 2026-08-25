import { useEffect, useMemo, useRef, useState } from 'react';
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

export interface EstimatedWordTiming {
  word: string;
  startSeconds: number;
}

/**
 * ESTIMATE ONLY — linear interpolation, not real word-level ASR timing.
 *
 * The backend STT (`audio_service.transcribe_audio_file`) returns a single
 * transcript string per ~30-60s chunk with no per-word timestamps, so there
 * is no ground truth for when any individual word was actually spoken.
 * This splits the chunk's transcript on whitespace and gives every word an
 * equal time-slice of `durationSeconds / wordCount`. That's inaccurate for
 * any one word (speech isn't evenly paced), but it makes captions advance
 * roughly in step with the audio instead of sitting as one static block for
 * the whole chunk. Never treat `startSeconds` here as exact sync.
 */
export function estimateWordTimings(text: string, durationSeconds: number): EstimatedWordTiming[] {
  const words = text.trim().length > 0 ? text.trim().split(/\s+/) : [];
  if (words.length === 0 || !(durationSeconds > 0)) {
    return words.map((word) => ({ word, startSeconds: 0 }));
  }
  const secondsPerWord = durationSeconds / words.length;
  return words.map((word, index) => ({ word, startSeconds: index * secondsPerWord }));
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
  // Playback time within the CURRENT chunk (seconds since that chunk's
  // `<audio>` started), used to drive the word-by-word caption estimate
  // below. Reset to 0 whenever the chunk changes.
  const [chunkPlaybackSeconds, setChunkPlaybackSeconds] = useState(0);
  const audioContainerRef = useRef<HTMLDivElement>(null);

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

  const currentChunk =
    playableChunks.length > 0 ? playableChunks[Math.min(currentIndex, playableChunks.length - 1)] : undefined;

  // Reset sub-chunk playback time whenever the current chunk changes (new
  // chunk starts from 0), then bind a native `timeupdate` listener directly
  // to the underlying `<audio>` DOM node. `AudioPlayerElement` (ai-elements
  // audio-player.tsx) renders a real `<audio slot="media">` element with no
  // React ref forwarding and media-chrome's `MediaController` exposes no
  // React context for `currentTime`, so the reliable hook is native DOM:
  // look up the `<audio>` node under our container and listen directly.
  useEffect(() => {
    setChunkPlaybackSeconds(0);
    const container = audioContainerRef.current;
    if (!container) return undefined;
    const audioEl = container.querySelector('audio');
    if (!audioEl) return undefined;
    const handleTimeUpdate = () => setChunkPlaybackSeconds(audioEl.currentTime);
    audioEl.addEventListener('timeupdate', handleTimeUpdate);
    return () => audioEl.removeEventListener('timeupdate', handleTimeUpdate);
  }, [currentChunk?.name]);

  // Per-chunk word timing estimate (see estimateWordTimings docs above) and
  // the index of the word considered "current" given chunkPlaybackSeconds.
  const wordTimings = useMemo(
    () => estimateWordTimings(currentChunk?.transcript_text || '', currentChunk?.duration_seconds || 0),
    [currentChunk?.transcript_text, currentChunk?.duration_seconds],
  );
  const activeWordIndex = useMemo(() => {
    let index = -1;
    for (let i = 0; i < wordTimings.length; i += 1) {
      if (wordTimings[i].startSeconds <= chunkPlaybackSeconds) {
        index = i;
      } else {
        break;
      }
    }
    return index;
  }, [wordTimings, chunkPlaybackSeconds]);

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
      <div ref={audioContainerRef} className="flex items-center gap-2">
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
          ) : wordTimings.length > 0 ? (
            // Karaoke-style progressive reveal: words estimated (see
            // estimateWordTimings) to have already been "said" by
            // chunkPlaybackSeconds render fully bright/bold, the rest stay
            // dim. Chosen over showing only a rolling word window because
            // it keeps the full caption visible (no layout jitter) while
            // still visually tracking playback progress.
            <p className="flex-1 text-center text-sm">
              {wordTimings.map((timing, index) => (
                <span
                  key={index}
                  className={cn(
                    'transition-colors',
                    index <= activeWordIndex ? 'font-semibold text-white' : 'text-white/50',
                  )}
                >
                  {timing.word}
                  {index < wordTimings.length - 1 ? ' ' : ''}
                </span>
              ))}
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
