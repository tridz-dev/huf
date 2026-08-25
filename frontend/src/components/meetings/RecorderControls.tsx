import { Mic, MicOff, Pause, Play, Square } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { RecorderStatus } from '@/hooks/useMeetingRecorder';

interface RecorderControlsProps {
  status: RecorderStatus;
  isMuted: boolean;
  onPause: () => void;
  onResume: () => void;
  onToggleMute: () => void;
  onRequestStop: () => void;
  disabled?: boolean;
}

/**
 * Pause/Resume is the primary control; Mute is a secondary icon toggle
 * kept visually distinct so it never competes with Pause/Stop (PLAN.md
 * G.1 "Recorder UX", G.2 item 5 — Mute and Pause stay semantically and
 * visually separate controls).
 */
export function RecorderControls({
  status,
  isMuted,
  onPause,
  onResume,
  onToggleMute,
  onRequestStop,
  disabled,
}: RecorderControlsProps) {
  const isRecording = status === 'recording';
  const isPaused = status === 'paused';

  return (
    <div className="flex items-center justify-center gap-4">
      <Button
        type="button"
        variant="outline"
        size="icon"
        className="h-12 w-12 rounded-full"
        onClick={onToggleMute}
        disabled={disabled || (!isRecording && !isPaused)}
        aria-label={isMuted ? 'Unmute microphone' : 'Mute microphone'}
        aria-pressed={isMuted}
      >
        {isMuted ? <MicOff className="h-5 w-5" /> : <Mic className="h-5 w-5" />}
      </Button>

      {isPaused ? (
        <Button
          type="button"
          variant="display"
          size="lg"
          className="h-16 w-16 rounded-full p-0"
          onClick={onResume}
          disabled={disabled}
          aria-label="Resume recording"
        >
          <Play className="h-6 w-6" />
        </Button>
      ) : (
        <Button
          type="button"
          variant="display"
          size="lg"
          className="h-16 w-16 rounded-full p-0"
          onClick={onPause}
          disabled={disabled || !isRecording}
          aria-label="Pause recording"
        >
          <Pause className="h-6 w-6" />
        </Button>
      )}

      <Button
        type="button"
        variant="destructive-ghost"
        size="icon"
        className="h-12 w-12 rounded-full"
        onClick={onRequestStop}
        disabled={disabled}
        aria-label="Stop recording"
      >
        <Square className="h-5 w-5" />
      </Button>
    </div>
  );
}
