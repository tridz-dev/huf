import type { ComponentType } from 'react';
import type { GatewayDoc } from '@/services/gatewayApi';

export interface ProviderPanelProps {
  gateway: GatewayDoc;
  onChange?: (patch: Partial<GatewayDoc>) => void;
}

export interface ProviderPanel {
  id: string;
  title: string;
  component: ComponentType<ProviderPanelProps>;
}

const registry = new Map<string, ProviderPanel[]>();

export function registerProviderPanel(provider: string, panel: ProviderPanel): void {
  const key = provider.toLowerCase();
  const panels = registry.get(key) ?? [];
  registry.set(key, [...panels.filter((p) => p.id !== panel.id), panel]);
}

export function getProviderPanels(provider: string | undefined | null): ProviderPanel[] {
  return registry.get((provider ?? '').toLowerCase()) ?? [];
}

// Append-only: one import line per panel module, each calling registerProviderPanel().
