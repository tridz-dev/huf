export type CatalogKind = 'channels' | 'integrations';

/**
 * Where "create a new record for this service" should go. Decided by the entry
 * point the user came from (the Integrations page or the Gateways page), never
 * by the service's own surface, so a flow started under Integrations stays there.
 */
export function getNewSettingRoute(kind: CatalogKind, serviceName: string): string {
  const base = kind === 'channels' ? '/gateways' : '/integrations';
  return `${base}/new?service=${encodeURIComponent(serviceName)}`;
}
