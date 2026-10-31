import { useCallback, useEffect, useRef, useState } from 'react';
import { FileText, Loader2, Radio, Timer } from 'lucide-react';
import { GatewayTest } from './GatewayTest';
import { Button } from '@/components/ui/button';
import { triggerResult } from '@/lib/flow-test/triggerResult';
import { ageText } from '@/lib/flow-test/testModel';
import { parseServerDate } from '@/lib/serverTime';
import { getLastWebhookRequest } from '@/services/flow/triggerApi';
import { getDocumentSample, listRecentDocuments, type RecentDocument, type StepTestResult } from '@/services/flow/stepTestApi';

const POLL_MS = 2000;
const WAIT_LIMIT_MS = 60_000;

interface Props {
  flowId: string;
  nodeId: string;
  kind: 'webhook' | 'schedule' | 'doc-event' | 'unset' | 'gateway' | 'whatsapp' | 'telegram' | null;
  doctype?: string | null;
  live: boolean;
  running: boolean;
  onResult: (result: StepTestResult) => void;
  onTick: () => void;
}

const messageOf = (error: unknown, fallback: string) => (error instanceof Error && error.message ? error.message : fallback);

/**
 * The Test tab of a trigger. It does not run anything: it brings in the data the flow starts with, from a request
 * that arrives (a web address), the last one received, a recent document or a pretend schedule tick. The result is
 * shown and pinned like any step's output, so the steps after it can offer real values.
 */
export function TriggerTestSection(props: Props) {
  switch (props.kind) {
    case 'webhook':
      return <WebhookTest {...props} />;
    case 'doc-event':
      return <DocumentTest {...props} />;
    case 'schedule':
      return <ScheduleTest {...props} />;
    case 'gateway':
    case 'whatsapp':
    case 'telegram':
      return <GatewayTest flowId={props.flowId} nodeId={props.nodeId} kind={props.kind} onResult={props.onResult} />;
    default:
      return (
        <p className="rounded-md border border-dashed border-border p-3 text-sm text-muted-foreground" data-testid="flow-step-test-trigger-unset">
          Choose what starts this flow on the Setup tab first. Then you can bring in sample data here.
        </p>
      );
  }
}

function WebhookTest({ flowId, live, onResult }: Props) {
  const [waiting, setWaiting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const stop = useCallback(() => {
    if (timer.current) clearInterval(timer.current);
    timer.current = null;
    setWaiting(false);
  }, []);
  useEffect(() => stop, [stop]);

  const useLast = async () => {
    setBusy(true);
    setNote(null);
    try {
      const last = await getLastWebhookRequest(flowId);
      if (last.found && last.sample) onResult(triggerResult(last.sample, `The last request this flow received${last.received_at ? `, ${ageText(parseServerDate(last.received_at))}` : ''}`));
      else setNote('Nothing has called this web address yet. Send a request to it, or wait for one here.');
    } catch (error) {
      setNote(messageOf(error, 'Could not load the last request.'));
    } finally {
      setBusy(false);
    }
  };

  const wait = async () => {
    setNote(null);
    let baseline: string | null = null;
    try {
      baseline = (await getLastWebhookRequest(flowId)).received_at;
    } catch (error) {
      setNote(messageOf(error, 'Could not start waiting.'));
      return;
    }
    setWaiting(true);
    const started = Date.now();
    timer.current = setInterval(async () => {
      try {
        const last = await getLastWebhookRequest(flowId);
        if (last.found && last.sample && last.received_at !== baseline) {
          stop();
          onResult(triggerResult(last.sample, 'The request that just arrived'));
          return;
        }
      } catch {
        // A hiccup while waiting: the next check tries again.
      }
      if (Date.now() - started > WAIT_LIMIT_MS) {
        stop();
        setNote('No request arrived in a minute. Send one to the web address on the Setup tab, then try again.');
      }
    }, POLL_MS);
  };

  return (
    <div className="space-y-3" data-testid="flow-step-test-webhook">
      {!live && (
        <p className="rounded-md border border-warning/30 bg-warning-tint p-2.5 text-xs text-warning" data-testid="flow-step-test-not-live">
          The web address only answers while the flow is Live. Publish the flow to receive requests, or paste a sample on the Setup tab.
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <Button type="button" onClick={waiting ? stop : wait} disabled={busy} data-testid="flow-step-test-wait">
          {waiting ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" aria-hidden /> : <Radio className="mr-1.5 h-4 w-4" aria-hidden />}
          {waiting ? 'Stop waiting' : 'Wait for a test request'}
        </Button>
        <Button type="button" variant="outline" onClick={useLast} disabled={busy || waiting} data-testid="flow-step-test-last">
          Use last received request
        </Button>
      </div>
      {waiting && (
        <p role="status" className="text-xs text-muted-foreground" data-testid="flow-step-test-waiting">
          Waiting for a request. Send one to the web address on the Setup tab. This stops after a minute.
        </p>
      )}
      {note && <p role="status" className="text-xs text-muted-foreground" data-testid="flow-step-test-trigger-note">{note}</p>}
    </div>
  );
}

function DocumentTest({ flowId, nodeId, doctype, onResult }: Props) {
  const [docs, setDocs] = useState<RecentDocument[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const load = async () => {
    setBusy('list');
    setNote(null);
    try {
      const found = await listRecentDocuments(flowId, nodeId);
      setDocs(found.documents);
      if (found.documents.length === 0) setNote('There are no documents of this type that you can open yet.');
    } catch (error) {
      setNote(messageOf(error, 'Could not load recent documents.'));
    } finally {
      setBusy(null);
    }
  };

  const pick = async (doc: RecentDocument) => {
    setBusy(doc.name);
    setNote(null);
    try {
      const out = await getDocumentSample(flowId, nodeId, doc.name);
      onResult(triggerResult(out.sample, `${doc.title}, as this flow would receive it`));
    } catch (error) {
      setNote(messageOf(error, 'Could not open that document.'));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-3" data-testid="flow-step-test-docevent">
      {!doctype ? (
        <p className="rounded-md border border-dashed border-border p-3 text-sm text-muted-foreground" data-testid="flow-step-test-no-doctype">
          Choose the kind of document this flow watches on the Setup tab first.
        </p>
      ) : (
        <>
          <Button type="button" onClick={load} disabled={busy === 'list'} data-testid="flow-step-test-docs">
            {busy === 'list' ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" aria-hidden /> : <FileText className="mr-1.5 h-4 w-4" aria-hidden />}
            Pick a recent document
          </Button>
          {docs && docs.length > 0 && (
            <ul className="space-y-1" aria-label="Recent documents" data-testid="flow-step-test-doc-list">
              {docs.map((doc) => (
                <li key={doc.name}>
                  <button
                    type="button"
                    className="flex w-full items-center justify-between gap-3 rounded-md border border-border px-3 py-2 text-left text-sm hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60"
                    onClick={() => pick(doc)}
                    disabled={busy !== null}
                    data-testid={`flow-step-test-doc-${doc.name}`}
                  >
                    <span className="min-w-0 break-words">{doc.title}</span>
                    <span className="shrink-0 text-meta text-muted-foreground">{ageText(parseServerDate(doc.modified))}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
      {note && <p role="status" className="text-xs text-muted-foreground" data-testid="flow-step-test-trigger-note">{note}</p>}
    </div>
  );
}

function ScheduleTest({ running, onTick }: Props) {
  return (
    <div className="space-y-3" data-testid="flow-step-test-schedule">
      <Button type="button" onClick={onTick} disabled={running} data-testid="flow-step-test-tick">
        {running ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" aria-hidden /> : <Timer className="mr-1.5 h-4 w-4" aria-hidden />}
        Simulate a tick
      </Button>
      <p className="text-xs text-muted-foreground">Pretends the schedule just fired, so you can see the data the steps after it get. Nothing is started.</p>
    </div>
  );
}
