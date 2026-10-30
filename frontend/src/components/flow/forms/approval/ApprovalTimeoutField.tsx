import { useState } from 'react';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '../../../ui/alert-dialog';
import { DurationField } from '../fields';
import { edgeRoute } from '../../../../services/flowSerializer';
import { durationWords, type TimeUnit } from '@/lib/flow-data/flowUnits';
import { useFlowContext } from '../../../../contexts/FlowContext';

const UNITS: TimeUnit[] = ['minutes', 'hours', 'days'];

/**
 * "If nobody answers, stop waiting after": the time limit of an approval, in minutes, hours or days, with what happens
 * at the end. The "Timed out" path exists only while a limit is set: clearing it removes that connection (asking first
 * when a step is connected to it). Lives in the step's Settings tab; the Setup tab says what it is set to.
 */
export function ApprovalTimeoutField({
  nodeId, kind, timeoutMs, onChange, disabled,
}: {
  nodeId: string;
  /** Contract type of the step, for test ids (`flow-field-<kind>-timeout_ms`). */
  kind: string;
  timeoutMs: number | undefined;
  onChange: (ms: number | undefined) => void;
  disabled?: boolean;
}) {
  const { activeFlow, updateEdges } = useFlowContext();
  const timedOut = (activeFlow?.edges ?? []).filter((e) => e.source === nodeId && edgeRoute(e) === 'timeout');
  const [confirmClear, setConfirmClear] = useState(false);
  const [redraw, setRedraw] = useState(0);

  const change = (ms: number | undefined) => {
    if (ms === undefined && timedOut.length > 0) {
      setConfirmClear(true);
      return;
    }
    onChange(ms);
  };
  const clearBoth = () => {
    updateEdges((activeFlow?.edges ?? []).filter((e) => !(e.source === nodeId && edgeRoute(e) === 'timeout')));
    onChange(undefined);
    setConfirmClear(false);
  };
  return (
    <>
      <DurationField
        key={redraw}
        id="approval-timeout"
        testId={`flow-field-${kind}-timeout_ms`}
        label="If nobody answers, stop waiting after"
        units={UNITS}
        perUnit={1000}
        placeholder="Wait as long as it takes"
        value={timeoutMs}
        onChange={change}
        disabled={disabled}
        hintTestId="flow-hint-approval-timeout"
        hint={
          timeoutMs !== undefined
            ? `After ${durationWords(timeoutMs / 1000, UNITS)} with no answer, the flow carries on along the "Timed out" path.${timedOut.length > 0 ? '' : ' Connect a step to that path.'}`
            : 'Leave empty to wait as long as it takes. If you set a time, a "Timed out" path appears for what should happen then.'
        }
      />
      <AlertDialog open={confirmClear} onOpenChange={setConfirmClear}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove the "Timed out" path?</AlertDialogTitle>
            <AlertDialogDescription>
              A step is connected to the "Timed out" path. Without a time limit that path is not used, so its connection will be removed. The step itself stays on the canvas.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="flow-approval-timeout-keep" onClick={() => setRedraw((n) => n + 1)}>Keep the time limit</AlertDialogCancel>
            <AlertDialogAction data-testid="flow-approval-timeout-clear" onClick={clearBoth}>Remove the path</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
