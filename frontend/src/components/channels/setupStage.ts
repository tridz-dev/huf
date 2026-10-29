// Ordered pre-live stages from PLAN 4.1; value = steps done of the 6-step wizard.
const STAGE_STEP: Record<string, number> = {
  not_connected: 1,
  connected_unverified: 2,
  receiving: 3,
  live_unrouted: 5,
};

export const SETUP_TOTAL_STEPS = 6;

/** Step number for a pre-live stage, or null when live/unknown/missing. */
export function setupStep(stage: string | null | undefined): number | null {
  if (!stage || stage === 'live' || stage === 'off') return null;
  return STAGE_STEP[stage] ?? null;
}

