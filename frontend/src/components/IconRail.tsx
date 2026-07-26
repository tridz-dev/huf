import * as React from "react"
import { type LucideIcon } from "lucide-react"

import { cn } from "@/lib/utils"

/**
 * Shared collapsed icon rail — a presentational mirror of the main app
 * sidebar's collapsed (icon) state: 48px wide, bg-sidebar, 32px square
 * icon buttons with the same hover/active treatment as the collapsed
 * SidebarMenuButton (see components/ui/sidebar.tsx). Used by the Hub page
 * so hub↔dashboard switching has no layout shift or color pop.
 */

export interface IconRailItem {
  key: string
  icon: LucideIcon
  label: string
  active?: boolean
  onClick?: () => void
}

interface IconRailButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  icon: LucideIcon
  label: string
  active?: boolean
}

export const IconRailButton = React.forwardRef<
  HTMLButtonElement,
  IconRailButtonProps
>(function IconRailButton({ icon: Icon, label, active, className, ...props }, ref) {
  return (
    <button
      ref={ref}
      type="button"
      title={label}
      aria-label={label}
      data-active={active || undefined}
      className={cn(
        // Mirrors the collapsed SidebarMenuButton variant exactly
        "flex size-8 items-center justify-center rounded-none p-2 text-steel transition-colors",
        "hover:bg-paper hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring",
        "data-[active=true]:bg-panel data-[active=true]:text-ink data-[active=true]:border-l-2 data-[active=true]:border-signal data-[active=true]:ring-1 data-[active=true]:ring-inset data-[active=true]:ring-line",
        className,
      )}
      {...props}
    >
      <Icon className="size-4 shrink-0" strokeWidth={1.6} />
    </button>
  )
})

interface IconRailProps {
  /** Top slot — brand mark (matches AppSidebarHeader's collapsed mark). */
  header?: React.ReactNode
  /** Slot under the header, e.g. New chat / recent chats. */
  actions?: React.ReactNode
  /** Primary nav items, rendered as IconRailButtons. */
  items?: IconRailItem[]
  /** Bottom slot, separated by a top border (like SidebarFooter). */
  footer?: React.ReactNode
  className?: string
}

export function IconRail({
  header,
  actions,
  items,
  footer,
  className,
}: IconRailProps) {
  return (
    <aside
      className={cn(
        "flex h-full w-12 flex-shrink-0 flex-col bg-sidebar border-r border-sidebar-border",
        className,
      )}
    >
      {header && <div className="flex flex-col p-2">{header}</div>}
      {actions && (
        <div className="flex flex-col items-center gap-1 px-2 pb-2">
          {actions}
        </div>
      )}
      {items && items.length > 0 && (
        <nav className="flex flex-1 flex-col items-center gap-1 overflow-y-auto p-2">
          {items.map(({ key, ...item }) => (
            <IconRailButton key={key} {...item} />
          ))}
        </nav>
      )}
      {footer && (
        <div className="flex flex-col items-center gap-1 border-t border-sidebar-border p-2">
          {footer}
        </div>
      )}
    </aside>
  )
}
