import { useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"

import { usePermissions } from "@/contexts/PermissionsContext"
import { useKeyboardShortcut } from "@/lib/shortcuts/useKeyboardShortcut"
import {
  dashboardNavItems,
  useNavItems,
  buildNavItems,
  knowNavItems,
  operateNavItems,
  settingsNavGroups,
  filterItemsByCapability,
} from "@/components/app-sidebar"
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog"
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command"

/**
 * Global Cmd+K (Ctrl+K on Windows/Linux) command palette.
 *
 * Nav entries are sourced directly from `app-sidebar.tsx` — the same arrays
 * that render the collapsible rail — and run through the sidebar's own
 * `filterItemsByCapability` mechanism, so the palette can never surface a
 * destination the rail itself would hide from the current user.
 */
export function CommandPalette() {
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()
  const { hasCapability, isLoading } = usePermissions()

  useKeyboardShortcut({ key: "k", mod: true }, () => setOpen((prev) => !prev))

  const groups = useMemo(() => {
    // `settingsNavGroups` holds heterogeneous item arrays, so `group.items` is
    // a union and the generic cannot infer one T. Narrowed the same way
    // app-sidebar.tsx does at its own call site, so both consumers agree.
    const settingsItems = settingsNavGroups.flatMap((group) =>
      filterItemsByCapability(
        group.items as Array<
          (typeof group.items)[number] & { capability: string | string[] | null }
        >,
        hasCapability,
        isLoading,
      ),
    )

    return [
      {
        label: "General",
        items: filterItemsByCapability(dashboardNavItems, hasCapability, isLoading),
      },
      { label: "Use", items: filterItemsByCapability(useNavItems, hasCapability, isLoading) },
      { label: "Build", items: filterItemsByCapability(buildNavItems, hasCapability, isLoading) },
      { label: "Know", items: filterItemsByCapability(knowNavItems, hasCapability, isLoading) },
      {
        label: "Operate",
        items: filterItemsByCapability(operateNavItems, hasCapability, isLoading),
      },
      { label: "Settings", items: settingsItems },
    ].filter((group) => group.items.length > 0)
  }, [hasCapability, isLoading])

  const handleSelect = (url: string) => {
    setOpen(false)
    navigate(url)
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="overflow-hidden p-0">
        <DialogTitle className="sr-only">Command palette</DialogTitle>
        <Command className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-muted-foreground [&_[cmdk-group]:not([hidden])_~[cmdk-group]]:pt-0 [&_[cmdk-group]]:px-2">
          <CommandInput placeholder="Jump to a page..." />
          <CommandList>
            <CommandEmpty>No results found.</CommandEmpty>
            {groups.map((group) => (
              <CommandGroup key={group.label} heading={group.label}>
                {group.items.map((item) => (
                  <CommandItem
                    key={item.url}
                    value={item.title}
                    onSelect={() => handleSelect(item.url)}
                  >
                    <item.icon className="h-4 w-4 shrink-0" strokeWidth={1.6} />
                    <span>{item.title}</span>
                  </CommandItem>
                ))}
              </CommandGroup>
            ))}
          </CommandList>
        </Command>
      </DialogContent>
    </Dialog>
  )
}
