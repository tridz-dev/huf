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
  const [sharingTabAudio, setSharingTabAudio] = useState(false);
  const [resumeDialogOpen, setResumeDialogOpen] = useState(false);
  const [resumeDialogLoading, setResumeDialogLoading] = useState(false);
  const [showTabAudioStoppedBanner, setShowTabAudioStoppedBanner] = useState(false);
  const hasStartedRef = useRef(false);
  const prevTabAudioActiveRef = useRef(false);

  const recorder = useMeetingRecorder({
    meetingName: meetingId ?? null,
    onError: (error) => {
      toast.error('Recording issue', { description: error.message });
    },
  });

  const { status, isMuted, elapsedSeconds, pendingUploadCount, minutesRecorded, resumableMeeting, tabAudioActive, start, pause, resume, toggleMute, shareTabAudio, resumeQueuedUploads, discardQueuedUploads } =
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

  // Show resume dialog if there's a resumable meeting and it doesn't match current meetingId
  useEffect(() => {
    if (resumableMeeting && meetingId && resumableMeeting.meetingName !== meetingId) {
      setResumeDialogOpen(true);
    }
  }, [resumableMeeting, meetingId]);

  // Register beforeunload guard while actively recording
  useEffect(() => {
    if (status === 'recording' || status === 'paused') {
      const handleBeforeUnload = (event: BeforeUnloadEvent) => {
        event.returnValue = true;
      };
      window.addEventListener('beforeunload', handleBeforeUnload);
      return () => {
        window.removeEventListener('beforeunload', handleBeforeUnload);
      };
    }
  }, [status]);

  // Track tab audio state transitions to show banner when it stops while recording
  useEffect(() => {
    if (prevTabAudioActiveRef.current && !tabAudioActive && status === 'recording') {
      setShowTabAudioStoppedBanner(true);
      // Auto-dismiss banner after 6 seconds
      const timer = setTimeout(() => {
        setShowTabAudioStoppedBanner(false);
      }, 6000);
      return () => clearTimeout(timer);
    }
    prevTabAudioActiveRef.current = tabAudioActive;
  }, [tabAudioActive, status]);

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

  const handleShareTabAudio = async () => {
    setSharingTabAudio(true);
    try {
      await shareTabAudio();
    } finally {
      setSharingTabAudio(false);
    }
  };

  const handleResumeRecording = async () => {
    if (!resumableMeeting) return;
    setResumeDialogLoading(true);
    try {
      await resumeQueuedUploads(resumableMeeting.meetingName, { manual: true });
      toast.success('Uploads resumed', {
        description: 'Your recording segments are now being uploaded.',
      });
      setResumeDialogOpen(false);
    } catch (error) {
      toast.error('Could not resume uploads', {
        description: error instanceof Error ? error.message : 'An unexpected error occurred.',
      });
    } finally {
      setResumeDialogLoading(false);
    }
  };

  const handleDiscardRecording = async () => {
    if (!resumableMeeting) return;
    setResumeDialogLoading(true);
    try {
      await discardQueuedUploads(resumableMeeting.meetingName);
      toast.info('Recording discarded', {
        description: 'The unfinished recording has been deleted.',
      });
      setResumeDialogOpen(false);
    } catch (error) {
      toast.error('Could not discard recording', {
        description: error instanceof Error ? error.message : 'An unexpected error occurred.',
      });
    } finally {
      setResumeDialogLoading(false);
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

      {/* Tab audio controls and indicator */}
      {(status === 'recording' || status === 'paused') && (
        <div className="flex flex-col items-center gap-3">
          {!tabAudioActive && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleShareTabAudio}
              disabled={sharingTabAudio}
            >
              {sharingTabAudio ? 'Enabling tab audio...' : 'Share tab audio'}
            </Button>
          )}
          {tabAudioActive && (
            <div className="rounded-full bg-green-100 px-3 py-1 text-xs font-medium text-green-800">
              Tab audio included
            </div>
          )}
        </div>
      )}

      {/* Tab audio stopped banner */}
      {showTabAudioStoppedBanner && (
        <div className="rounded-md bg-amber-50 px-4 py-3 text-sm text-amber-900 border border-amber-200">
          Tab audio stopped. Recording continues with mic only.
        </div>
      )}

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

      <AlertDialog open={resumeDialogOpen} onOpenChange={setResumeDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Resume unfinished recording?</AlertDialogTitle>
            <AlertDialogDescription>
              An unfinished recording from a previous session was found. Would you like to resume
              uploading it, or discard it?
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel
              onClick={(event) => {
                event.preventDefault();
                handleDiscardRecording();
              }}
              disabled={resumeDialogLoading}
            >
              Discard
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={(event) => {
                event.preventDefault();
                handleResumeRecording();
              }}
              disabled={resumeDialogLoading}
            >
              {resumeDialogLoading ? 'Resuming...' : 'Resume uploads'}
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
