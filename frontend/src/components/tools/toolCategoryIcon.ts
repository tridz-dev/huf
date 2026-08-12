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
  Slack,
  Github,
  Mail,
  Calendar,
  Table,
  FolderOpen,
  Video,
  MessageCircle,
  Terminal,
  KeyRound,
  UserPlus,
  Send,
  Gamepad2,
  Rss,
  type LucideIcon,
} from 'lucide-react';

/**
 * Icon for a tool group (an Agent Tool Type such as "Frappe Cloud", or a
 * connected-app service name such as "Slack" / "Gmail"). Matched on keywords
 * rather than exact names so groups added later still get a sensible icon
 * instead of falling back to the generic one. More specific patterns are
 * listed before broader ones so e.g. "Google Calendar" hits Calendar, not
 * the generic Google fallback.
 */
const KEYWORD_ICONS: Array<[RegExp, LucideIcon]> = [
  [/frappe cloud/i, Cloud],
  [/transcription/i, Mic],
  [/audio/i, AudioLines],
  [/ocr/i, ScanText],
  [/generation/i, Sparkles],
  [/serp|perplexity|web search/i, Search],
  [/places|maps/i, MapPin],
  [/calendar/i, Calendar],
  [/sheets?/i, Table],
  [/drive|storage/i, FolderOpen],
  [/meet|zoom/i, Video],
  [/gmail|email|mail/i, Mail],
  [/slack/i, Slack],
  [/github/i, Github],
  [/discord/i, Gamepad2],
  [/telegram/i, Send],
  [/whatsapp|messenger/i, MessageCircle],
  [/rss|feed/i, Rss],
  [/google/i, Globe],
  [/communication|raven|chat/i, MessageSquare],
  [/ssh|docker|sandbox|execution|terminal|script/i, Terminal],
  [/credential|secret|auth/i, KeyRound],
  [/recipient|contact/i, UserPlus],
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
