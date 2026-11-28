/**
 * Watches the background generation of an agent's default plan (multi-step runs).
 *
 * The plan is written server-side without saving the Agent, so the editor only needs to learn that it is
 * ready. While `active` (saved agent, multi-step on, plan still empty) the status is polled; `onDone` fires
 * when the status turns `done` so the caller can refetch the behaviour section. A `done` or `failed` seen
 * right after switching multi-step on may belong to an earlier run (the toggle is not saved yet), so polling
 * continues for a while and picks up the new run.
 */
import { useEffect, useRef, useState } from 'react';
import { call } from '@/lib/frappe-sdk';

export type DefaultPlanState = 'idle' | 'generating' | 'done' | 'failed';
export interface DefaultPlanStatus { state: DefaultPlanState; error: string | null }

const STATUS_METHOD = 'huf.huf.doctype.agent.default_plan.get_default_plan_status';
const POLL_MS = 3000;
const MAX_QUIET_POLLS = 20; // about a minute without a running job before polling stops

export function useDefaultPlanStatus(agentId: string | undefined, active: boolean, onDone?: () => void): DefaultPlanStatus {
  const [status, setStatus] = useState<DefaultPlanStatus>({ state: 'idle', error: null });
  const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;

  useEffect(() => {
    if (!agentId || !active) { setStatus({ state: 'idle', error: null }); return; }
    let cancelled = false;
    let timer: number | undefined;
    let quietPolls = 0;
    let previous: DefaultPlanState = 'idle';
    const tick = async () => {
      let next: DefaultPlanStatus | null = null;
      try {
        const res = await call.get(STATUS_METHOD, { agent: agentId });
        const m = (res?.message ?? {}) as Partial<DefaultPlanStatus>;
        next = { state: (m.state ?? 'idle') as DefaultPlanState, error: m.error ?? null };
      } catch (e) {
        console.error('Default plan status check failed:', e);
      }
      if (cancelled) return;
      if (next) {
        setStatus(next);
        if (next.state === 'done' && previous !== 'done') onDoneRef.current?.();
        previous = next.state;
        quietPolls = next.state === 'generating' ? 0 : quietPolls + 1;
        if (quietPolls > MAX_QUIET_POLLS) return;
      }
      timer = window.setTimeout(() => void tick(), POLL_MS);
    };
    void tick();
    return () => { cancelled = true; if (timer) window.clearTimeout(timer); };
  }, [agentId, active]);

  return status;
}
