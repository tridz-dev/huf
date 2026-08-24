import { useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, ChevronDown, RotateCw, Settings } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { linkRoutes } from '@/lib/link-routes';
import type { Meeting } from '@/types/meeting.types';

const MEETING_SUMMARY_AGENT_NAME = 'Meeting Summary Agent';

export interface MeetingFailureCardProps {
  failedStep?: Meeting['failed_step'];
  lastError?: string;
  errorLog?: string;
  onRetry: () => void;
  retrying: boolean;
}

/**
 * Failed-meeting state: shows why the meeting failed (distinguishing an
 * unconfigured AI model from an actual transcription/summary error), an
 * optional expandable error log, and the Retry action.
 */
export function MeetingFailureCard({ failedStep, lastError, errorLog, onRetry, retrying }: MeetingFailureCardProps) {
  const [logOpen, setLogOpen] = useState(false);
  const isModelNotConfigured = failedStep === 'Model Not Configured';

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-destructive/30 bg-destructive/5 p-4">
      <div className="flex items-start gap-2 text-sm text-destructive">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
        <div className="flex flex-col gap-1">
          {isModelNotConfigured ? (
            <>
              <span>No AI model is configured for this meeting's summary agent.</span>
              <span className="font-body text-xs text-steel">
                Ask an admin to configure a model in Agent settings, then retry.
              </span>
            </>
          ) : (
            <p className="font-body text-sm text-destructive">
              {lastError ||
                (failedStep === 'Transcription'
                  ? 'Transcription failed for this meeting.'
                  : 'Summarizing this meeting failed.')}
            </p>
          )}
        </div>
      </div>

      {!!errorLog && (
        <Collapsible open={logOpen} onOpenChange={setLogOpen}>
          <CollapsibleTrigger asChild>
            <Button variant="ghost" size="sm" className="h-auto w-fit gap-1 p-0 font-body text-xs text-steel">
              <ChevronDown className={logOpen ? 'h-3.5 w-3.5 rotate-180 transition-transform' : 'h-3.5 w-3.5 transition-transform'} aria-hidden />
              View error log
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <pre className="mt-2 max-h-48 overflow-auto rounded-md border border-line bg-card p-2 font-mono text-xs text-steel">
              {errorLog}
            </pre>
          </CollapsibleContent>
        </Collapsible>
      )}

      <div className="flex items-center gap-2">
        {isModelNotConfigured && (
          <Button size="sm" variant="default" asChild>
            <Link to={linkRoutes.agent(MEETING_SUMMARY_AGENT_NAME)}>
              <Settings className="h-3.5 w-3.5" aria-hidden />
              Configure model
            </Link>
          </Button>
        )}
        <Button size="sm" variant="outline" onClick={onRetry} disabled={retrying}>
          <RotateCw className={retrying ? 'h-3.5 w-3.5 animate-spin' : 'h-3.5 w-3.5'} aria-hidden />
          {retrying ? 'Retrying...' : 'Retry'}
        </Button>
      </div>
    </div>
  );
}
