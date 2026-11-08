import { useCallback, useEffect, useState } from 'react';
import { Loader2, MessageSquare } from 'lucide-react';
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
import { Badge, type BadgeProps } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { cancelExternalSession, listExternalSessions } from '@/services/externalAgentsApi';
import type { ExternalSession } from '@/types/externalAgents.types';
import { formatTimeAgo } from '@/utils/time';
import { SessionTranscriptDialog } from './SessionTranscriptDialog';

const POLL_INTERVAL_MS = 10_000;
const TERMINAL_STATES: ReadonlyArray<ExternalSession['state']> = ['Completed', 'Failed', 'Cancelled'];

const STATE_BADGE_VARIANT: Record<ExternalSession['state'], BadgeProps['variant']> = {
  Active: 'success',
  'Waiting for Input': 'secondary',
  'Waiting for Approval': 'secondary',
  'Runtime Offline': 'outline',
  Completed: 'outline',
  Failed: 'destructive',
  Cancelled: 'outline',
};

const VISIBILITY_COPY: Record<ExternalSession['visibility_mode'], { label: string; tip: string }> = {
  Connected: {
    label: 'Connected',
    tip: 'Huf records what this agent does through Huf. Anything it does on your own computer is not visible here.',
  },
  'Huf-managed': {
    label: 'Managed by Huf',
    tip: 'Huf runs and monitors this agent.',
  },
};

export function SessionsSection() {
  const [sessions, setSessions] = useState<ExternalSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [transcript, setTranscript] = useState<ExternalSession | null>(null);
  const [transcriptOpen, setTranscriptOpen] = useState(false);
  const [cancelTarget, setCancelTarget] = useState<ExternalSession | null>(null);
  const [cancelling, setCancelling] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const rows = await listExternalSessions(50);
      setSessions(rows);
      setLoadError(false);
    } catch {
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const intervalId = window.setInterval(() => void refresh(), POLL_INTERVAL_MS);
    return () => window.clearInterval(intervalId);
  }, [refresh]);

  function openTranscript(session: ExternalSession) {
    setTranscript(session);
    setTranscriptOpen(true);
  }

  async function confirmCancel() {
    if (!cancelTarget) return;
    setCancelling(true);
    try {
      await cancelExternalSession(cancelTarget.name);
      toast.success('Session cancelled');
      setCancelTarget(null);
      await refresh();
    } catch (e) {
      toast.error(getFrappeErrorMessage(e));
    } finally {
      setCancelling(false);
    }
  }

  // Use the freshest copy of the open session so its state stays current while the transcript is open.
  const transcriptSession = transcript
    ? (sessions.find((s) => s.name === transcript.name) ?? transcript)
    : null;

  return (
    <TooltipProvider>
      <section aria-labelledby="agent-sessions-heading" className="space-y-3">
        <h2 id="agent-sessions-heading" className="text-base font-semibold text-foreground">
          Agent sessions
        </h2>

        <Card>
          <CardContent className="p-0">
            {loading && sessions.length === 0 ? (
              <p className="px-4 py-6 text-sm text-muted-foreground">Loading sessions...</p>
            ) : loadError && sessions.length === 0 ? (
              <p className="px-4 py-6 text-sm text-muted-foreground">
                We couldn't load sessions. Trying again shortly.
              </p>
            ) : sessions.length === 0 ? (
              <div className="flex flex-col items-center gap-2 px-4 py-10 text-center">
                <MessageSquare className="h-6 w-6 text-muted-foreground" />
                <p className="text-sm text-muted-foreground">
                  No sessions yet. They appear when a connected agent starts working.
                </p>
              </div>
            ) : (
              <ul className="divide-y">
                {sessions.map((session) => {
                  const visibility = VISIBILITY_COPY[session.visibility_mode];
                  const isTerminal = TERMINAL_STATES.includes(session.state);
                  return (
                    <li
                      key={session.name}
                      className="flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
                    >
                      <div className="min-w-0 space-y-1.5">
                        <p className="truncate text-sm font-medium text-foreground" title={session.agent}>
                          {session.agent}
                        </p>
                        <div className="flex flex-wrap items-center gap-1.5">
                          <Badge variant={STATE_BADGE_VARIANT[session.state]}>{session.state}</Badge>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Badge variant="outline">{visibility.label}</Badge>
                            </TooltipTrigger>
                            <TooltipContent>{visibility.tip}</TooltipContent>
                          </Tooltip>
                          <span className="text-xs text-muted-foreground">
                            {formatTimeAgo(session.ended_at ?? session.creation)}
                          </span>
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        <Button variant="outline" size="sm" onClick={() => openTranscript(session)}>
                          Open
                        </Button>
                        {!isTerminal && (
                          <Button variant="ghost" size="sm" onClick={() => setCancelTarget(session)}>
                            Cancel
                          </Button>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </CardContent>
        </Card>
      </section>

      {transcriptSession && (
        <SessionTranscriptDialog
          session={transcriptSession}
          open={transcriptOpen}
          onOpenChange={setTranscriptOpen}
        />
      )}

      <AlertDialog open={!!cancelTarget} onOpenChange={(open) => !open && !cancelling && setCancelTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Cancel this session?</AlertDialogTitle>
            <AlertDialogDescription>
              {cancelTarget ? `${cancelTarget.agent} will stop working on this session.` : ''}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={cancelling}>Keep running</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault();
                void confirmCancel();
              }}
              disabled={cancelling}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {cancelling && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Cancel session
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </TooltipProvider>
  );
}
