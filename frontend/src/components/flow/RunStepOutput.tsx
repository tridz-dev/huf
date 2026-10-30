import { Badge } from '@/components/ui/badge';
import { HumanValue } from '@/components/common/HumanValue';
import { asCodeStepOutput, titleNodeIds, withoutFailureKeys } from '@/lib/flow-run/flowRunFormat';
import { humanize } from '@/lib/flow-run/humanize';
import { redactSecrets, summarizeToolOutput } from '@/lib/flow/flowToolSummary';

/** Keys an approval step's output carries: its sentence ("Approved by Ana on ...") already says all of them. */
const DECISION_KEYS = ['decision', 'comment', 'decided_by', 'decided_at'];

const isEmpty = (o: unknown) => o === undefined || o === null || o === '' || (typeof o === 'object' && Object.keys(o as object).length === 0);

export interface RunStepOutputProps {
    stepId: string;
    output: unknown;
    /** The step failed and its reason is already shown above, so the status / error keys are left out. */
    reasonShown: boolean;
    failed: boolean;
    /** The approval sentence is shown for this step: its decision keys are not repeated as rows. */
    decisionShown: boolean;
    /** Step id -> step title: ids inside the data read as titles. */
    names: Record<string, string>;
    titleOf: (id: string) => string | null;
    /** Registered tool of an integration step, for its one-line summary. */
    toolId?: string;
    /** The trigger input when this is the first step, shown here instead of in a block of its own. */
    dataReceived?: unknown;
    /** The step's data when its sentence already says everything: only the "{ } Raw" control is offered for it. */
    rawOutput?: unknown;
}

const EXIT_WORDS: Record<string, string> = { Ok: 'Finished normally', Error: 'Stopped with an error', Timeout: 'Took too long and was stopped' };

/**
 * What a finished step produced: a plain summary line for integration steps, labelled rows for everything else,
 * with the exact data behind "{ } Raw". Tokens and auth headers never reach the screen.
 */
export function RunStepOutput({ stepId, output, reasonShown, failed, decisionShown, names, titleOf, toolId, dataReceived, rawOutput }: RunStepOutputProps) {
    const shown = titleNodeIds(failed && reasonShown ? withoutFailureKeys(output) : output, titleOf);
    const merged = dataReceived !== undefined;
    if (isEmpty(shown) && !(merged && humanize(dataReceived).kind !== 'empty')) {
        if (rawOutput === undefined || isEmpty(rawOutput)) return null;
        return (
            <HumanValue value={undefined} raw rawValue={redactSecrets(titleNodeIds(rawOutput, titleOf))} testId={`flow-run-human-${stepId}`} rawTitle="Raw data of this step" rawTextTestId={`flow-run-step-output-${stepId}`} />
        );
    }
    const useInput = merged && humanize(shown).kind === 'empty';
    const safe = redactSecrets(useInput ? dataReceived : shown);
    const summary = failed ? null : summarizeToolOutput(toolId, output);
    const codeOut = asCodeStepOutput(safe);

    if (codeOut) {
        return (
            <div className="mt-2 space-y-2" data-testid={`flow-run-step-output-${stepId}`}>
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <Badge variant={codeOut.exitStatus === 'Ok' ? 'success' : 'destructive'} data-testid="flow-code-output-exit">{EXIT_WORDS[codeOut.exitStatus] ?? codeOut.exitStatus}</Badge>
                </div>
                <div>
                    <div className="text-xs text-muted-foreground mb-1">Printed output</div>
                    {codeOut.stdout ? (
                        <pre data-testid="flow-code-output-stdout" className="max-h-60 overflow-auto whitespace-pre-wrap rounded bg-muted p-2 font-mono text-xs">{codeOut.stdout}</pre>
                    ) : (
                        <p className="text-xs text-muted-foreground" data-testid="flow-code-output-stdout-empty">Nothing was printed.</p>
                    )}
                </div>
                {codeOut.result !== undefined && codeOut.result !== null && (
                    <div>
                        <div className="text-xs text-muted-foreground mb-1">Result</div>
                        <pre data-testid="flow-code-output-result" className="max-h-60 overflow-auto whitespace-pre-wrap rounded bg-muted p-2 font-mono text-xs">
                            {typeof codeOut.result === 'string' ? codeOut.result : JSON.stringify(codeOut.result, null, 2)}
                        </pre>
                    </div>
                )}
                {codeOut.truncated && (
                    <p className="text-xs text-warning" data-testid="flow-code-output-truncated">Output was cut off because it was too long.</p>
                )}
            </div>
        );
    }

    const human = (
        <HumanValue
            value={safe}
            names={names}
            hideKeys={decisionShown ? DECISION_KEYS : undefined}
            testId={`flow-run-human-${stepId}`}
            raw={typeof safe === 'object' && safe !== null}
            rawTitle="Raw data of this step"
            rawTextTestId={`flow-run-step-output-${stepId}`}
            className="mt-2"
        />
    );
    if (summary) {
        return (
            <>
                <div className="mt-1 text-sm" data-testid={`flow-run-summary-${stepId}`}>{summary}</div>
                <details className="mt-1" data-testid={`flow-run-raw-${stepId}`}>
                    <summary className="cursor-pointer text-xs text-muted-foreground hover:text-foreground">Show raw response</summary>
                    <pre data-testid={`flow-run-step-output-${stepId}`} className="mt-2 bg-muted p-2 rounded text-xs font-mono overflow-x-auto whitespace-pre-wrap">
                        {typeof safe === 'string' ? safe : JSON.stringify(safe, null, 2)}
                    </pre>
                </details>
            </>
        );
    }
    return (
        <>
            {merged && <div className="mt-2 text-xs text-muted-foreground" data-testid={`flow-run-received-${stepId}`}>What came in</div>}
            {human}
        </>
    );
}
