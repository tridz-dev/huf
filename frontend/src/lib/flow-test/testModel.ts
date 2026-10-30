/**
 * Words and small rules of the Test tab (UX-16): where a sample came from, how a button is named, how long ago
 * something was pinned. Pure, so it is tested without a browser.
 */

export type SampleSource = 'pinned' | 'trigger_sample' | 'last_run' | 'none' | 'edited';

export const SOURCE_LABEL: Record<SampleSource, string> = {
  pinned: 'From pinned sample',
  trigger_sample: 'From trigger sample',
  last_run: 'From last run',
  none: 'No sample yet',
  edited: 'Edited sample',
};

/** What the test needs to know about a step to name the button and the notes around it. */
export interface StepBehaviour {
  simulated: boolean;
  calls_ai: boolean;
  approval: boolean;
  trigger: boolean;
  trigger_kind?: string | null;
}

export function testButtonLabel(b: Pick<StepBehaviour, 'simulated'>): string {
  return b.simulated ? 'Test (simulated)' : 'Test step';
}

/** The one line under the button. */
export function testButtonHint(b: StepBehaviour): string {
  if (b.approval) return 'Nothing is sent. This shows the card the approver would see.';
  if (b.simulated) return 'Nothing is sent. The test shows what would happen.';
  if (b.calls_ai) return 'Asks the AI model for real. Anything the agent would send or change is skipped.';
  return 'Nothing is sent or changed. The step only reads and works with the sample.';
}

export const AI_NOTE = 'This step calls the AI model';

/** `5 min ago`, `just now`, `2 hours ago`, `3 days ago`. */
export function ageText(at: string | Date | null | undefined, now: number = Date.now()): string {
  if (!at) return '';
  const time = at instanceof Date ? at.getTime() : Date.parse(at);
  if (Number.isNaN(time)) return '';
  const seconds = Math.max(0, Math.round((now - time) / 1000));
  if (seconds < 45) return 'just now';
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return hours === 1 ? '1 hour ago' : `${hours} hours ago`;
  const days = Math.round(hours / 24);
  return days === 1 ? 'yesterday' : `${days} days ago`;
}

export function durationText(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '';
  if (ms < 1000) return `${Math.max(1, Math.round(ms))} ms`;
  const s = ms / 1000;
  return s < 10 ? `${s.toFixed(1)} s` : `${Math.round(s)} s`;
}

/** The edited sample text is usable when it is JSON for an object. */
export function parseSampleInput(text: string): { ok: true; value: Record<string, unknown> } | { ok: false; message: string } {
  try {
    const value = JSON.parse(text);
    if (!value || typeof value !== 'object' || Array.isArray(value)) return { ok: false, message: 'The sample has to be an object, like { "input": { ... } }.' };
    return { ok: true, value };
  } catch {
    return { ok: false, message: 'This is not valid JSON yet.' };
  }
}

const AI_CONFIRM_KEY = 'huf.steptest.ai-confirmed';

let confirmedThisSession = false;

/** Forget the answer (tests). */
export function resetAiConfirmed(): void {
  confirmedThisSession = false;
  try {
    window.localStorage.removeItem(AI_CONFIRM_KEY);
  } catch {
    // Nothing stored.
  }
}

/** The "this calls the AI model" question is asked once per browser (once per session where storage is blocked). */
export function aiAlreadyConfirmed(): boolean {
  if (confirmedThisSession) return true;
  try {
    return window.localStorage.getItem(AI_CONFIRM_KEY) === '1';
  } catch {
    return false;
  }
}

export function rememberAiConfirmed(): void {
  confirmedThisSession = true;
  try {
    window.localStorage.setItem(AI_CONFIRM_KEY, '1');
  } catch {
    // Blocked storage: the question is simply asked again next time.
  }
}
