import {
  ArchiveRestore,
  ArchiveX,
  CheckCircle2,
  CircleDashed,
  Clock,
  Database,
  FilePlus,
  FileText,
  Flag,
  GitBranch,
  GitFork,
  Globe,
  Mail,
  MessageCircle,
  MessageSquare,
  Repeat,
  RotateCw,
  Save,
  Send,
  Sheet,
  SquareAsterisk,
  Terminal,
  UserCheck,
  Webhook,
  Wrench,
  Zap,
  type LucideIcon,
} from 'lucide-react';
import { actionOptions } from '../../data/actions';
import { triggerOptions } from '../../data/triggers';
import { actionCardId } from '../../lib/flow/flowLabels';
import type { FlowNodeData } from '../../types/flow.types';

/**
 * One icon table for the palette, the canvas cards and the rail. Names come from data/actions.ts and
 * data/triggers.ts; the agent step is always SquareAsterisk (the product's agent icon), never a play triangle.
 */
export const NODE_ICONS: Record<string, LucideIcon> = {
  ArchiveRestore,
  ArchiveX,
  CheckCircle2,
  CircleDashed,
  Clock,
  Database,
  FilePlus,
  FileText,
  Flag,
  GitBranch,
  GitFork,
  Globe,
  Mail,
  MessageCircle,
  MessageSquare,
  Repeat,
  RotateCw,
  Save,
  Send,
  Sheet,
  SquareAsterisk,
  Terminal,
  UserCheck,
  Webhook,
  Wrench,
  Zap,
};

/** Icon for a palette entry (`flow-card-*` tiles). */
export function paletteIcon(name: string | undefined): LucideIcon {
  return (name && NODE_ICONS[name]) || CircleDashed;
}

/**
 * Icon for a card on the canvas. It follows the step's kind, not whatever icon name was stored with the
 * node, so every Run agent card looks the same everywhere.
 */
export function cardIcon(data: FlowNodeData): LucideIcon {
  if (data.nodeType === 'trigger') {
    const t = data.triggerConfig?.type;
    return paletteIcon(t ? triggerOptions.find((o) => o.id === t)?.icon : 'CircleDashed');
  }
  if (data.nodeType === 'end') return paletteIcon('Flag');
  const id = actionCardId(data.actionConfig as { type?: unknown; tool_id?: unknown } | undefined);
  const fromPalette = actionOptions.find((o) => o.id === id)?.icon;
  return paletteIcon(fromPalette ?? data.icon);
}
