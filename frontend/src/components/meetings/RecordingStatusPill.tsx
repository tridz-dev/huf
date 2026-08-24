import { Circle, Mic, MicOff, Pause } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import type { RecorderStatus } from '@/hooks/useMeetingRecorder';

interface RecordingStatusPillProps {
  status: RecorderStatus;
  isMuted: boolean;
}

/**
 * Persistent, high-contrast status pill for the active recorder. Never
 * relies on color alone — every state pairs an icon with a text label, per
 * PLAN.md G.1 accessibility requirements.
 */
export function RecordingStatusPill({ status, isMuted }: RecordingStatusPillProps) {
  if (status === 'recording' && isMuted) {
    return (
      <Badge variant="pill-warning" className="gap-1.5 px-3 py-1 text-[13px]">
        <MicOff className="h-3.5 w-3.5" aria-hidden />
        Muted
      </Badge>
    );
  }

  if (status === 'recording') {
    return (
      <Badge variant="pill-danger" className="gap-1.5 px-3 py-1 text-[13px]">
        <Circle className="h-2.5 w-2.5 animate-pulse fill-current" aria-hidden />
        Recording
      </Badge>
    );
  }

  if (status === 'paused') {
    return (
      <Badge variant="pill-neutral" className="gap-1.5 px-3 py-1 text-[13px]">
        <Pause className="h-3.5 w-3.5" aria-hidden />
        Paused
      </Badge>
    );
  }

  if (status === 'stopped') {
    return (
      <Badge variant="pill-neutral" className="gap-1.5 px-3 py-1 text-[13px]">
        <Mic className="h-3.5 w-3.5" aria-hidden />
        Stopped
      </Badge>
    );
  }

  return null;
}
