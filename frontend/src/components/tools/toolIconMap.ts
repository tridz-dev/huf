import { Bot, Code2, Globe, type LucideIcon } from 'lucide-react';
import { getCategoryIcon } from './toolCategoryIcon';

/**
 * Icon for an individual tool card. Prefers the tool's connected-app service
 * or curated tool type (via getCategoryIcon) so e.g. a Slack tool shows the
 * Slack icon; falls back to a coarse icon based on the raw operation type.
 */
export function getToolIconForType(types?: string, service?: string, toolType?: string): LucideIcon {
  if (service || toolType) return getCategoryIcon(service || toolType);
  if (types === 'GET' || types === 'POST') return Globe;
  if (types === 'Run Agent') return Bot;
  return Code2;
}

