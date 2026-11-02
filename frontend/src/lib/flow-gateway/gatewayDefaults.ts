import type { GatewayTriggerUiConfig, TriggerConfig } from '@/types/flow.types';
import type { GatewayChoice } from './gatewayTrigger.types';
import { gatewaysForKind, isGatewayKindId, type GatewayKindId } from './gatewayWords';

/**
 * The config a freshly chosen chat trigger starts with. When the person has exactly one usable number or bot it is
 * picked for them; otherwise the channel stays blank (a draft saves; publishing asks for it).
 */
export function newGatewayConfig(kind: GatewayKindId, gateways: readonly GatewayChoice[] | null | undefined): GatewayTriggerUiConfig {
  const usable = gatewaysForKind(kind, gateways ?? []).filter((g) => g.enabled);
  return usable.length === 1 ? { type: kind, gateway: usable[0].name } : { type: kind };
}

/** Whether a trigger counts as set up: every kind but a chat trigger is once chosen; a chat trigger needs its channel. */
export function triggerIsConfigured(config: TriggerConfig | undefined): boolean {
  if (!config?.type) return false;
  return isGatewayKindId(config.type) ? !!(config as GatewayTriggerUiConfig).gateway?.trim() : true;
}
