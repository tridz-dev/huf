import {
  Cloud,
  MessageSquare,
  Wrench,
  Search,
  Code,
  MapPin,
  Brain,
  FileText,
  Workflow,
  Package,
  Mic,
  AudioLines,
  ScanText,
  Sparkles,
  LifeBuoy,
  Users,
  Globe,
  type LucideIcon,
} from 'lucide-react';

/**
 * Icon for an Agent Tool Type (the curated, product-facing category such as
 * "Frappe Cloud" or "Communication Tools"). Matched on keywords rather than
 * exact names so categories added later still get a sensible icon instead of
 * falling back to the generic one.
 */
const KEYWORD_ICONS: Array<[RegExp, LucideIcon]> = [
  [/frappe cloud/i, Cloud],
  [/transcription/i, Mic],
  [/audio/i, AudioLines],
  [/ocr/i, ScanText],
  [/generation/i, Sparkles],
  [/serp|search/i, Search],
  [/places|maps/i, MapPin],
  [/google/i, Globe],
  [/communication|raven|chat/i, MessageSquare],
  [/builder/i, Wrench],
  [/developer/i, Code],
  [/memory/i, Brain],
  [/document|report/i, FileText],
  [/workflow|flow/i, Workflow],
  [/helpdesk|support/i, LifeBuoy],
  [/crm/i, Users],
  [/erpnext|inventory/i, Package],
];

export function getCategoryIcon(category?: string): LucideIcon {
  if (!category) return Wrench;
  const hit = KEYWORD_ICONS.find(([pattern]) => pattern.test(category));
  return hit ? hit[1] : Wrench;
}
