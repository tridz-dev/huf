import { useMemo, useState } from 'react';
import { Music } from 'lucide-react';
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

  return (
    <div className="flex flex-col gap-1.5">
      <AudioPlayer key={current.name}>
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
      {playableChunks.length > 1 && (
        <span className="font-body text-xs text-steel-soft">
          Part {currentIndex + 1} of {playableChunks.length}
        </span>
      )}
    </div>
  );
}
