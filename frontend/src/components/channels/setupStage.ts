// Pre-live stages from PLAN 4.1, in order. `rank` compares stages; `wizardStep` is the stepper
// position (1-6) the wizard resumes at; `setupStep` is the same number for the "n of 6" banner/card.
const STAGE_ORDER = ['not_connected', 'connected_unverified', 'receiving', 'live_unrouted', 'live'] as const;

export const SETUP_TOTAL_STEPS = 6;

export const SETUP_STEP_TITLES = [
  'Choose how to connect',
  'Credentials',
  'Webhook',
  'Test',
  'Who answers',
  'Access policy',
] as const;

/** Position of a stage in the setup flow, or -1 for off/blocked/degraded/unknown. */
export function stageRank(stage: string | null | undefined): number {
  return stage ? (STAGE_ORDER as readonly string[]).indexOf(stage) : -1;
}

const STAGE_STEP: Record<string, number> = {
  not_connected: 1,
  connected_unverified: 3,
  receiving: 4,
  live_unrouted: 5,
  live: 6,
};

/** Stepper position the wizard resumes at for a stage (1 when unknown). */
export function wizardStep(stage: string | null | undefined): number {
  return (stage && STAGE_STEP[stage]) || 1;
}

/** Step number for a pre-live stage, or null when live/off/unknown/missing. */
export function setupStep(stage: string | null | undefined): number | null {
  if (!stage || stage === 'live' || stage === 'off') return null;
  return STAGE_STEP[stage] ?? null;
}
