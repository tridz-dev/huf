import { useEffect, useState } from "react"
import { Check, ChevronsUpDown, LogOut, Moon, Sun, Monitor } from "lucide-react"

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
  const [colorScheme, setColorSchemeState] = useState<HufColorScheme>('light')

  useEffect(() => {
    setColorSchemeState(getColorScheme())
  }, [])

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
              {SCHEMES.map(({ id, label, icon: Icon }) => (
                <DropdownMenuItem
                  key={id}
                  onClick={() => handleSchemeChange(id)}
                  className="flex items-center justify-between"
                >
                  <span className="flex items-center">
                    <Icon className="mr-2 h-4 w-4" />
                    {label}
                  </span>
                  {colorScheme === id && (
                    <Check className="h-4 w-4 text-steel" />
                  )}
                </DropdownMenuItem>
              ))}
            </DropdownMenuGroup>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={logout} className="text-red-500 focus:text-red-700">
              <LogOut className="mr-2 h-4 w-4" />
              Log out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}
