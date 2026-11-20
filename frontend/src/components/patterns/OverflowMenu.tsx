/**
 * OverflowMenu (DESIGN.md §6.10.1, §6.10.4): the "…" menu for a page head or
 * a list row. Secondary and rare actions live here so the head keeps exactly
 * one primary action. Destructive items go last, after a separator.
 */
import type { LucideIcon } from 'lucide-react';
import { MoreHorizontal } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { cn } from '@/lib/utils';

export interface OverflowMenuItem {
  label: string;
  onSelect: () => void;
  icon?: LucideIcon;
  destructive?: boolean;
  disabled?: boolean;
  /** Draw a separator above this item (use before the destructive group). */
  separated?: boolean;
}

export interface OverflowMenuProps {
  items: OverflowMenuItem[];
  /** Accessible name, e.g. "More actions for Refund policy.pdf". */
  label?: string;
  size?: 'icon' | 'icon-sm';
  className?: string;
}

export function OverflowMenu({ items, label = 'More actions', size = 'icon', className }: OverflowMenuProps) {
  if (items.length === 0) return null;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button type="button" variant="ghost" size={size} aria-label={label} className={cn('text-steel', className)}>
          <MoreHorizontal className="h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <span key={item.label} className="contents">
              {item.separated && <DropdownMenuSeparator />}
              <DropdownMenuItem
                disabled={item.disabled}
                onSelect={item.onSelect}
                className={cn(item.destructive && 'text-destructive focus:text-destructive')}
              >
                {Icon && <Icon className="h-4 w-4" />}
                {item.label}
              </DropdownMenuItem>
            </span>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
