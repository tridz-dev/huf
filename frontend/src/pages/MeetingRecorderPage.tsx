import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import { RecorderTimer } from '@/components/meetings/RecorderTimer';
import { RecorderControls } from '@/components/meetings/RecorderControls';
import { RecordingStatusPill } from '@/components/meetings/RecordingStatusPill';
import { useMeetingRecorder } from '@/hooks/useMeetingRecorder';
import { stopRecording as stopRecordingApi } from '@/services/meetingApi';

/**
 * Active recording view. Calm/minimal on purpose (PLAN.md G.1 "Overall
 * product polish") — the timer is the dominant element, controls are large
 * touch targets, and there is no dense data on this screen.
 *
 * Recording starts automatically on mount (mic permission prompt included)
 * since the meeting itself was already created by `MeetingsHeaderActions`
 * before navigating here — Quick Start has zero intermediate screens.
 */
export default function MeetingRecorderPage() {
  const { meetingId } = useParams<{ meetingId: string }>();
  const navigate = useNavigate();
  const [confirmStopOpen, setConfirmStopOpen] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [announcement, setAnnouncement] = useState('');
  const hasStartedRef = useRef(false);

  const recorder = useMeetingRecorder({
    meetingName: meetingId ?? null,
    onError: (error) => {
      toast.error('Recording issue', { description: error.message });
    },
  });

  const { status, isMuted, elapsedSeconds, pendingUploadCount, minutesRecorded, start, pause, resume, toggleMute } =
    recorder;

  useEffect(() => {
    if (!meetingId || hasStartedRef.current) return;
    hasStartedRef.current = true;
    start().catch(() => {
      toast.error('Could not access your microphone', {
        description: 'Check your browser permissions and try again.',
      });
    });
  }, [meetingId, start]);

  useEffect(() => {
    if (status === 'recording') {
      setAnnouncement(isMuted ? 'Muted' : 'Recording');
    } else if (status === 'paused') {
      setAnnouncement('Paused');
    } else if (status === 'stopped') {
      setAnnouncement('Recording stopped');
    }
  }, [status, isMuted]);

  const handleStop = async () => {
    if (!meetingId) return;
    setStopping(true);
    try {
      await recorder.stop();
      await stopRecordingApi(meetingId);
      navigate(`/meetings/${meetingId}`);
    } catch (error) {
      toast.error('Could not stop recording', {
        description: error instanceof Error ? error.message : 'An unexpected error occurred.',
      });
    } finally {
      setStopping(false);
      setConfirmStopOpen(false);
    }
  };

  if (!meetingId) {
    return null;
  }

  const savedIndicatorLabel =
    pendingUploadCount > 0
      ? `${minutesRecorded} minute${minutesRecorded === 1 ? '' : 's'} recorded, saving...`
      : `${minutesRecorded} minute${minutesRecorded === 1 ? '' : 's'} recorded, all saved`;

  return (
    <div className="flex min-h-[70vh] flex-col items-center justify-center gap-10 px-4 py-16">
      <div aria-live="polite" className="sr-only">
        {announcement}
      </div>

      <RecordingStatusPill status={status} isMuted={isMuted} />

      <RecorderTimer elapsedSeconds={elapsedSeconds} paused={status === 'paused'} />

      <p className="text-sm text-steel">{savedIndicatorLabel}</p>

      <RecorderControls
        status={status}
        isMuted={isMuted}
        onPause={pause}
        onResume={() => {
          resume().catch(() => {
            toast.error('Could not resume recording', {
              description: 'Check your microphone permissions and try again.',
            });
          });
        }}
        onToggleMute={toggleMute}
        onRequestStop={() => setConfirmStopOpen(true)}
        disabled={status === 'stopped' || stopping}
      />

      <AlertDialog open={confirmStopOpen} onOpenChange={setConfirmStopOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Stop this recording?</AlertDialogTitle>
            <AlertDialogDescription>
              This ends the session. Everything recorded so far has been saved and will be
              transcribed and summarized next.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={stopping}>Keep recording</AlertDialogCancel>
            <AlertDialogAction
              onClick={(event) => {
                event.preventDefault();
                handleStop();
              }}
              disabled={stopping}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {stopping ? 'Stopping...' : 'Stop recording'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <Button variant="link" size="sm" onClick={() => navigate('/meetings')} disabled={stopping}>
        Back to meetings
      </Button>
    </div>
  );
}
