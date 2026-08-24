import { useState } from 'react';
import { Mic, Plus } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { NewMeetingDialog } from './NewMeetingDialog';
import { createMeeting, startRecording } from '@/services/meetingApi';

/**
 * Quick Start is a single click, zero intermediate screens: it creates the
 * meeting and navigates straight to the recorder, which itself requests
 * mic permission and starts capture on mount. "New meeting with details"
 * is the only path to the optional context dialog (PLAN.md G.1/G.2 item 1).
 */
export function MeetingsHeaderActions() {
  const navigate = useNavigate();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [quickStarting, setQuickStarting] = useState(false);
  const [starting, setStarting] = useState(false);

  const beginRecording = async (details: { title?: string; description?: string; participants?: string }) => {
    const { meeting_name: meetingName } = await createMeeting(details);
    await startRecording(meetingName);
    navigate(`/huf/meetings/${meetingName}/record`);
  };

  const handleQuickStart = async () => {
    setQuickStarting(true);
    try {
      await beginRecording({});
    } catch (error) {
      toast.error('Could not start recording', {
        description: error instanceof Error ? error.message : 'An unexpected error occurred.',
      });
    } finally {
      setQuickStarting(false);
    }
  };

  const handleStartWithDetails = async (details: { title?: string; description?: string; participants?: string }) => {
    setStarting(true);
    try {
      await beginRecording(details);
      setDialogOpen(false);
    } catch (error) {
      toast.error('Could not start recording', {
        description: error instanceof Error ? error.message : 'An unexpected error occurred.',
      });
    } finally {
      setStarting(false);
    }
  };

  return (
    <div className="flex items-center gap-2">
      <Button variant="outline" size="sm" onClick={() => setDialogOpen(true)} disabled={quickStarting}>
        <Plus className="w-4 h-4 mr-2" />
        New meeting with details
      </Button>
      <Button variant="display" size="sm" onClick={handleQuickStart} disabled={quickStarting}>
        <Mic className="w-4 h-4 mr-2" />
        {quickStarting ? 'Starting...' : 'Quick start'}
      </Button>
      <NewMeetingDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        onStart={handleStartWithDetails}
        starting={starting}
      />
    </div>
  );
}
