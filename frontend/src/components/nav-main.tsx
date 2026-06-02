import { ChevronRight, type LucideIcon } from "lucide-react"
import { NavLink, useLocation } from "react-router-dom"

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
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

export interface NavSection {
  label?: string
  items: {
    title: string
    url?: string
    icon?: LucideIcon
    capability?: string | null
    items?: {
      title: string
      url: string
      capability?: string | null
    }[]
  }[]
}

export function NavMain({
  sections,
}: {
  sections: NavSection[]
}) {
  const location = useLocation()
  const { isMobile, setOpenMobile } = useSidebar()

  const handleNavClick = () => {
    if (isMobile) {
      setOpenMobile(false)
    }
  }

  return (
    <>
      {sections.map((section, index) => (
        <SidebarGroup key={index}>
          {section.label && <SidebarGroupLabel>{section.label}</SidebarGroupLabel>}
          <SidebarMenu>
            {section.items.map((item) => {
              // Check if any sub-item is active
              const isSubItemActive = item.items?.some((subItem) => location.pathname === subItem.url || location.pathname.startsWith(subItem.url + '/')) || false
              const isActive = Boolean(isSubItemActive || (item.url && (location.pathname === item.url || (item.url !== '/' && location.pathname.startsWith(item.url + '/')))))

              if (item.items && item.items.length > 0) {
                return (
                  <Collapsible
                    key={item.title}
                    asChild
                    defaultOpen={isActive}
                    className="group/collapsible"
                  >
                    <SidebarMenuItem>
                      <CollapsibleTrigger asChild>
                        <SidebarMenuButton tooltip={item.title} isActive={isActive}>
                          {item.icon && <item.icon />}
                          <span>{item.title}</span>
                          <ChevronRight className="ml-auto transition-transform duration-200 group-data-[state=open]/collapsible:rotate-90" />
                        </SidebarMenuButton>
                      </CollapsibleTrigger>
                      <CollapsibleContent>
                        <SidebarMenuSub>
                          {item.items.map((subItem) => {
                            const isSubActive = location.pathname === subItem.url || location.pathname.startsWith(subItem.url + '/')
                            return (
                              <SidebarMenuSubItem key={subItem.title}>
                                <SidebarMenuSubButton asChild isActive={isSubActive}>
                                  <NavLink to={subItem.url} onClick={handleNavClick}>
                                    <span>{subItem.title}</span>
                                  </NavLink>
                                </SidebarMenuSubButton>
                              </SidebarMenuSubItem>
                            )
                          })}
                        </SidebarMenuSub>
                      </CollapsibleContent>
                    </SidebarMenuItem>
                  </Collapsible>
                )
              }

              return (
                <SidebarMenuItem key={item.title}>
                  <SidebarMenuButton asChild tooltip={item.title} isActive={isActive}>
                    {item.url ? (
                      <NavLink to={item.url} onClick={handleNavClick}>
                        {item.icon && <item.icon />}
                        <span>{item.title}</span>
                      </NavLink>
                    ) : (
                      <div>
                        {item.icon && <item.icon />}
                        <span>{item.title}</span>
                      </div>
                    )}
                  </SidebarMenuButton>
                </SidebarMenuItem>
              )
            })}
          </SidebarMenu>
        </SidebarGroup>
      ))}
    </>
  )
}
