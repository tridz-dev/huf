import {
  ArchiveRestore,
  ArchiveX,
  CheckCircle2,
  CircleDashed,
  Clock,
  Database,
  FilePen,
  FilePlus,
  FileSearch,
  FileText,
  Flag,
  GitBranch,
  GitFork,
  Globe,
  Hourglass,
  Mail,
  MessageCircle,
  MessageSquare,
  OctagonX,
  Puzzle,
  Repeat,
  RotateCw,
  Save,
  Send,
  Sheet,
  Split,
  SquareAsterisk,
  Terminal,
  UserCheck,
  UserPen,
  Webhook,
  Workflow,
  Wrench,
  Zap,
  type LucideIcon,
} from 'lucide-react';
import { findActionOption } from '../../lib/flow-graph/appNodeTypes';
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
  FilePen,
  FilePlus,
  FileSearch,
  FileText,
  Flag,
  GitBranch,
  GitFork,
  Globe,
  Hourglass,
  Mail,
  MessageCircle,
  MessageSquare,
  OctagonX,
  Puzzle,
  Repeat,
  RotateCw,
  Save,
  Send,
  Sheet,
  Split,
  SquareAsterisk,
  Terminal,
  UserCheck,
  UserPen,
  Webhook,
  Workflow,
  Wrench,
  Zap,
};

/** Icon for a palette entry (`flow-card-*` tiles). */
export function paletteIcon(name: string | undefined): LucideIcon {
  if (!name) return CircleDashed;
  // An app writes its step icon as a lucide name in any common spelling (message-square, messageSquare); an unknown one is a Puzzle.
  const pascal = name.replace(/(^|[-_ ]+)([a-zA-Z0-9])/g, (_m, _s, c: string) => c.toUpperCase());
  return NODE_ICONS[name] ?? NODE_ICONS[pascal] ?? Puzzle;
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
  const id = actionCardId(data.actionConfig as { type?: unknown; tool_id?: unknown; backend_type?: unknown } | undefined);
  const fromPalette = findActionOption(id)?.icon;
  return paletteIcon(fromPalette ?? data.icon);
}
