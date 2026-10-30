import { useState } from 'react';
import { Check, Copy } from 'lucide-react';
import { copyText } from '@/lib/clipboard';
import { formatAbsoluteTime } from '@/lib/serverTime';
import { runTimesSentence } from '@/lib/flow-run/flowTimeZone';
import { runDuration } from '@/lib/flow-run/story/time';
import type { FlowRunDetail } from '@/services/flowApi';

interface RunDetailsFoldProps {
  run: FlowRunDetail;
  runId: string;
  siteZone: string | null;
  stepCount: number;
  lastStep: string;
  startedWords: string;
}

function Row({ label, testId, children }: { label: string; testId?: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-steel">{label}</dt>
      <dd className="break-words text-sm text-ink" data-testid={testId}>{children}</dd>
    </div>
  );
}

/** The facts few people need (run id, exact times, time zone), folded away under "Details". */
export function RunDetailsFold({ run, runId, siteZone, stepCount, lastStep, startedWords }: RunDetailsFoldProps) {
  const [copied, setCopied] = useState(false);
  const took = runDuration(run.started_at, run.completed_at);
  return (
    <details className="rounded-lg border border-line bg-panel px-4 py-3 text-sm" data-testid="flow-run-details-fold">
      <summary className="cursor-pointer select-none font-medium text-ink" data-testid="flow-run-details-toggle">Details</summary>
      <dl className="mt-3 grid grid-cols-1 gap-x-4 gap-y-3 sm:grid-cols-2" data-testid="flow-run-meta">
        <Row label="Flow" testId="flow-run-flow-name">{run.flow_name || run.flow_id}</Row>
        <Row label="Started by" testId="flow-run-trigger">{startedWords}</Row>
        <Row label="Started" testId="flow-run-started">{formatAbsoluteTime(run.started_at)}</Row>
        {run.completed_at && <Row label="Finished" testId="flow-run-finished">{formatAbsoluteTime(run.completed_at)}</Row>}
        {took && <Row label="Took" testId="flow-run-duration">{took}</Row>}
        <Row label="Steps run" testId="flow-run-step-count">{stepCount}</Row>
        {lastStep && <Row label="Last step" testId="flow-run-current-node">{lastStep}</Row>}
        <Row label="Run id" testId="flow-run-id">
          <span className="inline-flex items-center gap-1.5">
            <span className="font-mono text-xs">{runId}</span>
            <button
              type="button"
              className="rounded p-0.5 text-steel hover:text-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              aria-label="Copy run id"
              data-testid="flow-run-id-copy"
              onClick={() => { void copyText(runId).then((ok) => { if (ok) { setCopied(true); window.setTimeout(() => setCopied(false), 1500); } }); }}
            >
              {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
            </button>
          </span>
        </Row>
      </dl>
      <p className="mt-3 text-meta text-steel" data-testid="flow-run-timezone-note">{runTimesSentence(siteZone)}</p>
    </details>
  );
}
