import type { GatewayKindId } from '@/lib/flow-gateway/gatewayWords';

/** Read-only facts under a chat trigger's options: they are always true, so they are notes, not settings. */
export const TRIGGER_NOTES: Record<GatewayKindId, string[]> = {
  gateway: ['People who ask to stop messages never start this.'],
  whatsapp: [
    'People who reply STOP never start this.',
    'A reply sent more than 24 hours after their message needs an approved template.',
  ],
  telegram: ['In groups the bot only sees every message when its privacy mode is off or it is an admin.'],
};
