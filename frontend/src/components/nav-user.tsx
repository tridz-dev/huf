import { useState } from "react"
import { ChevronsUpDown, LogOut, Moon, Sun, Monitor } from "lucide-react"

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar"
import { useUser } from "@/contexts/UserContext"
import { getInitials } from "@/utils/getInitials"
import UserAvatar from "./UserAvatar"
import {
  getColorScheme,
  setColorScheme,
  type HufColorScheme,
} from "@/lib/personalization"

const SCHEMES: { id: HufColorScheme; label: string; icon: typeof Sun }[] = [
  { id: 'light', label: 'Light', icon: Sun },
  { id: 'dark', label: 'Dark', icon: Moon },
  { id: 'system', label: 'System', icon: Monitor },
];

export function NavUser() {
  const { isMobile } = useSidebar()
  const { logout, user } = useUser()
  // Lazy-initialize from the persisted value instead of a hardcoded default
  // + a mount effect that corrects it a tick later. NavUser sits inside the
  // per-route subtree that App.tsx remounts on every navigation (the
  // AnimatePresence wrapper there is keyed on `location.pathname`), so a
  // hardcoded default here would flash "Light" as selected on every route
  // change even while the app is actually in dark mode, until the effect
  // caught up. Reading the source of truth synchronously at mount time
  // removes that window entirely.
  const [colorScheme, setColorSchemeState] = useState<HufColorScheme>(getColorScheme)

  if (!user) {
    return null;
  }

  const displayName = user.full_name || user.name;
  const displayEmail = user.email || '';

  const handleSchemeChange = (scheme: HufColorScheme) => {
    setColorSchemeState(scheme)
    setColorScheme(scheme)
  }

  return (
    <SidebarMenu>
      <SidebarMenuItem className="group-data-[collapsible=icon]:flex group-data-[collapsible=icon]:justify-center">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <SidebarMenuButton
              size="lg"
              className="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground group-data-[collapsible=icon]:justify-center"
            >
              <div className="flex h-[30px] w-[30px] flex-none items-center justify-center rounded-full bg-line text-ink overflow-hidden">
                {user.user_image ? (
                  <img
                    src={user.user_image}
                    alt={displayName}
                    className="h-full w-full object-cover"
                  />
                ) : (
                  <span className="font-mono text-[11px]">
                    {getInitials(displayName)}
                  </span>
                )}
              </div>
              <div className="grid flex-1 text-left leading-tight group-data-[collapsible=icon]:hidden">
                <span className="truncate font-body text-[13px] font-semibold text-ink">
                  {displayName}
                </span>
                {displayEmail && (
                  <span className="truncate font-mono text-[10.5px] text-steel">
                    {displayEmail}
                  </span>
                )}
              </div>
              <ChevronsUpDown className="ml-auto size-4 text-steel-soft group-data-[collapsible=icon]:hidden" />
            </SidebarMenuButton>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            className="w-[--radix-dropdown-menu-trigger-width] min-w-56 rounded-lg"
            side={isMobile ? "bottom" : "right"}
            align="end"
            sideOffset={4}
          >
            <DropdownMenuLabel className="p-0 font-normal">
              <div className="flex items-center gap-2 px-1 py-1.5 text-left text-sm">
                <UserAvatar />
                <div className="grid flex-1 text-left text-sm leading-tight">
                  <span className="truncate font-semibold">{displayName}</span>
                  {displayEmail && (
                    <span className="truncate text-xs">{displayEmail}</span>
                  )}
                </div>
              </div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuGroup>
              <DropdownMenuLabel className="text-xs text-steel-soft px-2 py-1.5 font-normal">
                Appearance
              </DropdownMenuLabel>
              <div className="px-2 py-2">
                <div className="relative flex w-full h-8 rounded-full border border-line bg-panel p-1">
                  {/* Sliding thumb background */}
                  <div
                    className="absolute inset-y-1 bg-ink rounded-full pointer-events-none"
                    style={{
                      width: 'calc((100% - 8px) / 3)',
                      transform: `translateX(calc(4px + ${SCHEMES.findIndex(s => s.id === colorScheme)} * (100% / 3 - 8px / 3)))`,
                      transition: 'transform 200ms ease',
                    }}
                  />

                  {/* Segment buttons */}
                  {SCHEMES.map(({ id, label, icon: Icon }) => (
                    <button
                      key={id}
                      type="button"
                      onClick={() => handleSchemeChange(id)}
                      className={`relative z-10 flex-1 flex items-center justify-center gap-1 text-xs font-medium transition-colors rounded-[calc(var(--r-full)-2px)] ${
                        colorScheme === id ? 'text-paper' : 'text-steel'
                      }`}
                    >
                      <Icon className="w-3.5 h-3.5" />
                      <span>{label}</span>
                    </button>
                  ))}
                </div>
              </div>
            </DropdownMenuGroup>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={logout} className="text-destructive focus:text-destructive">
              <LogOut className="mr-2 h-4 w-4" />
              Log out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}
