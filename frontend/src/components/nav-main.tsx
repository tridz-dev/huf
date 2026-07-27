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

export function NavMain({
  items,
  label,
}: {
  items: {
    title: string
    url: string
    icon?: LucideIcon
    count?: number
    badge?: string
  }[]
  label?: string
}) {
  const location = useLocation()
  const { isMobile, setOpenMobile } = useSidebar()

  const handleNavClick = () => {
    if (isMobile) {
      setOpenMobile(false)
    }
  }

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
                <NavLink to={item.url} onClick={handleNavClick} className="flex w-full items-center gap-2">
                  {item.icon && <item.icon strokeWidth={1.6} />}
                  <span className="font-body text-[13.5px]">{item.title}</span>
                  {(item.badge || typeof item.count === 'number') && (
                    <div className="ml-auto flex items-center gap-1.5 group-data-[collapsible=icon]:hidden">
                      {item.badge && (
                        <span className="font-mono text-[8.5px] uppercase tracking-wider px-1.5 py-0.5 rounded-none border border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400 font-medium">
                          {item.badge}
                        </span>
                      )}
                      {typeof item.count === 'number' && (
                        <span className="font-mono text-[10.5px] text-steel-soft">
                          {item.count}
                        </span>
                      )}
                    </div>
                  )}
                </NavLink>
              </SidebarMenuButton>
            </SidebarMenuItem>
          )
        })}
      </SidebarMenu>
    </SidebarGroup>
  )
}
