import { Bot, Code2, Globe, type LucideIcon } from 'lucide-react';

export function getToolIconForType(types?: string): LucideIcon {
  if (types === 'GET' || types === 'POST') return Globe;
  if (types === 'Run Agent') return Bot;
  return Code2;
}

