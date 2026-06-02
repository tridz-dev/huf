import { type LucideIcon } from "lucide-react"
import { NavLink, useLocation } from "react-router-dom"

import {
  SidebarGroup,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar"

export interface NavSection {
  label?: string
  items: {
    title: string
    url: string
    icon?: LucideIcon
    capability?: string | null
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
              // For nested routes (like /knowledge/sources), checking prefix is good.
              // For exact matching you might need a different strategy, but prefix works for most.
              const isActive = location.pathname === item.url ||
                (item.url !== '/' && location.pathname.startsWith(item.url))

              return (
                <SidebarMenuItem key={item.title}>
                  <SidebarMenuButton asChild tooltip={item.title} isActive={isActive}>
                    <NavLink to={item.url} onClick={handleNavClick}>
                      {item.icon && <item.icon />}
                      <span>{item.title}</span>
                    </NavLink>
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
