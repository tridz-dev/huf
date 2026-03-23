import * as React from "react"
import { Home, Bot, Workflow, Database, Plug, MessageSquare, Zap, Server, ScrollText, Users } from "lucide-react"
import { useLocation } from "react-router-dom"

import { NavMain } from "@/components/nav-main"
import { NavUser } from "@/components/nav-user"
import { AppSidebarHeader } from "@/components/app-sidebar-header"
import { ChatSidebarContent } from "@/components/chat/ChatSidebarContent"
import { usePermissions } from "@/contexts/PermissionsContext"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarRail,
  useSidebar,
} from "@/components/ui/sidebar"

/**
 * Each nav item may declare an optional `capability` string.
 * If present the item is hidden from users who don't have that capability.
 * Items with capability === null are always visible (e.g. Dashboard).
 */
const allNavItems = [
  {
    title: "Dashboard",
    url: "/",
    icon: Home,
    capability: null,
  },
  {
    title: "Chat",
    url: "/chat",
    icon: MessageSquare,
    capability: "chat.use",
  },
  {
    title: "Agents",
    url: "/agents",
    icon: Bot,
    capability: "agent.use",
  },
  {
    title: "Executions",
    url: "/executions",
    icon: Zap,
    capability: "agent.use",
  },
  {
    title: "Flows",
    url: "/flows",
    icon: Workflow,
    capability: "flows.use",
  },
  {
    title: "Data",
    url: "/data",
    icon: Database,
    capability: "agent.view_all",
  },
  {
    title: "AI Providers",
    url: "/providers",
    icon: Plug,
    capability: "system.providers.manage",
  },
  {
    title: "MCP Servers",
    url: "/mcp",
    icon: Server,
    capability: "system.mcp.manage",
  },
  {
    title: "Users",
    url: "/users",
    icon: Users,
    capability: "users.manage",
  },
  {
    title: "Agent Prompts",
    url: "/prompts",
    icon: ScrollText,
    capability: "agent.use",
  },
]

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const location = useLocation()
  const { isMobile } = useSidebar()
  const { hasCapability, isLoading } = usePermissions()
  const isChatPage = location.pathname.startsWith('/chat')

  // Show chat list in sidebar on mobile when on chat page
  const showChatList = isMobile && isChatPage

  // While permissions are loading show only uncapability-gated items so the
  // sidebar doesn't flash/jump once capabilities resolve.
  const navItems = isLoading
    ? allNavItems.filter((item) => item.capability === null)
    : allNavItems.filter(
        (item) => item.capability === null || (item.capability && hasCapability(item.capability)),
      )

  return (
    <Sidebar collapsible="icon" {...props}>
      <SidebarHeader>
        <AppSidebarHeader />
      </SidebarHeader>
      <SidebarContent>
        <NavMain items={navItems} />
        {showChatList && <ChatSidebarContent />}
      </SidebarContent>
      <SidebarFooter>
        <NavUser />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
