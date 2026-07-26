import { ChevronRight, type LucideIcon } from "lucide-react"
import { NavLink, useLocation } from "react-router-dom"

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  SidebarGroup,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  useSidebar,
} from "@/components/ui/sidebar"

export interface NavCollapsibleItem {
  title: string
  url: string
  icon?: LucideIcon
}

/**
 * A collapsible sidebar group (two-level nav). Expanded sidebar: an accordion
 * section whose open state is owned by the parent so only one group is open
 * at a time. Collapsed icon rail: the group becomes a flyout popover so its
 * sub-items stay reachable without expanding the rail.
 */
export function NavCollapsibleGroup({
  title,
  icon: Icon,
  items,
  open,
  onOpenChange,
}: {
  title: string
  icon: LucideIcon
  items: NavCollapsibleItem[]
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const location = useLocation()
  const { isMobile, setOpenMobile, state } = useSidebar()

  const isItemActive = (url: string) =>
    location.pathname === url || location.pathname.startsWith(url + "/")
  const isActive = items.some((item) => isItemActive(item.url))

  const handleNavClick = () => {
    if (isMobile) {
      setOpenMobile(false)
    }
  }

  if (state === "collapsed") {
    return (
      <SidebarGroup>
        <SidebarMenu>
          <SidebarMenuItem>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <SidebarMenuButton tooltip={title} isActive={isActive}>
                  <Icon />
                  <span>{title}</span>
                </SidebarMenuButton>
              </DropdownMenuTrigger>
              <DropdownMenuContent side="right" align="start" sideOffset={16} className="w-48">
                <DropdownMenuLabel>{title}</DropdownMenuLabel>
                <DropdownMenuSeparator />
                {items.map((item) => (
                  <DropdownMenuItem key={item.title} asChild>
                    <NavLink
                      to={item.url}
                      onClick={handleNavClick}
                      className={isItemActive(item.url) ? "bg-accent text-accent-foreground font-medium" : ""}
                    >
                      {item.title}
                    </NavLink>
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarGroup>
    )
  }

  return (
    <SidebarGroup>
      <SidebarMenu>
        <Collapsible open={open} onOpenChange={onOpenChange} className="group/collapsible">
          <SidebarMenuItem>
            <CollapsibleTrigger asChild>
              <SidebarMenuButton tooltip={title} isActive={isActive}>
                <Icon />
                <span>{title}</span>
                <ChevronRight className="ml-auto transition-transform duration-200 group-data-[state=open]/collapsible:rotate-90" />
              </SidebarMenuButton>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <SidebarMenuSub>
                {items.map((item) => (
                  <SidebarMenuSubItem key={item.title}>
                    <SidebarMenuSubButton asChild isActive={isItemActive(item.url)}>
                      <NavLink to={item.url} onClick={handleNavClick}>
                        {item.icon && <item.icon />}
                        <span>{item.title}</span>
                      </NavLink>
                    </SidebarMenuSubButton>
                  </SidebarMenuSubItem>
                ))}
              </SidebarMenuSub>
            </CollapsibleContent>
          </SidebarMenuItem>
        </Collapsible>
      </SidebarMenu>
    </SidebarGroup>
  )
}
