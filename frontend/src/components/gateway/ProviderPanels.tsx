import type { GatewayDoc } from '@/services/gatewayApi';
import { getProviderPanels } from './panels';

interface ProviderPanelsProps {
  gateway: GatewayDoc;
  onChange?: (patch: Partial<GatewayDoc>) => void;
}

export function ProviderPanels({ gateway, onChange }: ProviderPanelsProps) {
  const panels = getProviderPanels(gateway.provider);
  if (panels.length === 0) return null;
  return (
    <>
      {panels.map(({ id, title, component: Panel }) => (
        <section key={id} aria-label={title} className="space-y-2 rounded-lg border p-4">
          <p className="text-sm font-medium">{title}</p>
          <Panel gateway={gateway} onChange={onChange} />
        </section>
      ))}
    </>
  );
}
