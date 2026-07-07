import { ChevronRight, Settings, type LucideIcon } from "lucide-react"
import { NavLink, useLocation } from "react-router-dom"

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import {
  SidebarGroup,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  useSidebar,
} from "@/components/ui/sidebar"

type NavItem = {
  title: string
  url: string
  icon?: LucideIcon
}

export function NavMain({
  items,
  settingsItems,
  label,
}: {
  items: NavItem[]
  settingsItems?: NavItem[]
  label?: string
}) {
  const location = useLocation()
  const { isMobile, setOpenMobile } = useSidebar()

  const handleNavClick = () => {
    if (isMobile) {
      setOpenMobile(false)
    }
  }

  const isSettingsActive = settingsItems?.some((item) => location.pathname.startsWith(item.url)) ?? false

  return (
    <SidebarGroup>
      {label && <SidebarGroupLabel>{label}</SidebarGroupLabel>}
      <SidebarMenu>
        {items.map((item) => {
          const isActive = location.pathname === item.url ||
            (item.url !== '/' && location.pathname.startsWith(item.url))

          return (
            <SidebarMenuItem key={item.title}>
              <SidebarMenuButton asChild tooltip={item.title} isActive={isActive}>
                <NavLink to={item.url} onClick={handleNavClick}>
                  {item.icon && <item.icon strokeWidth={1.6} />}
                  <span className="font-body text-[13.5px]">{item.title}</span>
                </NavLink>
              </SidebarMenuButton>
            </SidebarMenuItem>
          )
        })}
        {settingsItems && settingsItems.length > 0 && (
          <Collapsible asChild defaultOpen={isSettingsActive} className="group/settings">
            <SidebarMenuItem>
              <CollapsibleTrigger asChild>
                <SidebarMenuButton tooltip="Settings" isActive={isSettingsActive}>
                  <Settings strokeWidth={1.6} />
                  <span className="font-body text-[13.5px]">Settings</span>
                  <ChevronRight className="ml-auto transition-transform group-data-[state=open]/settings:rotate-90" />
                </SidebarMenuButton>
              </CollapsibleTrigger>
              <CollapsibleContent>
                <SidebarMenuSub>
                  {settingsItems.map((item) => {
                    const isActive = location.pathname.startsWith(item.url)
                    return (
                      <SidebarMenuSubItem key={item.title}>
                        <SidebarMenuSubButton asChild isActive={isActive}>
                          <NavLink to={item.url} onClick={handleNavClick}>
                            {item.icon && <item.icon strokeWidth={1.6} />}
                            <span>{item.title}</span>
                          </NavLink>
                        </SidebarMenuSubButton>
                      </SidebarMenuSubItem>
                    )
                  })}
                </SidebarMenuSub>
              </CollapsibleContent>
            </SidebarMenuItem>
          </Collapsible>
        )}
      </SidebarMenu>
    </SidebarGroup>
  )
}
