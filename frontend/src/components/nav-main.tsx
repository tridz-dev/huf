import { FlaskConical, type LucideIcon } from "lucide-react"
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
                {/*
                  No `w-full` here: SidebarMenuButton's own base class already
                  sets it, and repeating it via Slot's plain className
                  concatenation puts a second width declaration after the
                  collapsed-rail's fixed 38px width, which is exactly the kind
                  of callsite-beats-component override that keeps the rail from
                  sizing correctly.
                */}
                <NavLink to={item.url} onClick={handleNavClick} className="flex items-center gap-2">
                  {item.icon && <item.icon strokeWidth={1.6} />}
                  <span className="font-body text-[13.5px] group-data-[collapsible=icon]:hidden">
                    {item.title}
                  </span>
                  {(item.badge || typeof item.count === 'number') && (
                    <div className="ml-auto flex items-center gap-1.5 group-data-[collapsible=icon]:hidden">
                      {item.badge && (
                        <span
                          title={item.badge}
                          aria-label={item.badge}
                          role="img"
                          className="flex items-center text-steel-soft dark:text-steel opacity-70 hover:opacity-100 transition-opacity"
                        >
                          <FlaskConical className="!size-[12.5px]" strokeWidth={1.5} />
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
