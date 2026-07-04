import * as React from "react"
import { Home, Bot, Workflow, Database, Plug, MessageSquare, Zap, Server, ScrollText, Users, BookOpen, Cpu, Link2, Terminal, Settings, ChevronRight } from "lucide-react"
import { NavLink, useLocation } from "react-router-dom"

import { NavMain } from "@/components/nav-main"
import { NavUser } from "@/components/nav-user"
import { AppSidebarHeader } from "@/components/app-sidebar-header"
import { ChatSidebarContent } from "@/components/chat/ChatSidebarContent"
import { usePermissions } from "@/contexts/PermissionsContext"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
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
    title: "Agents",
    url: "/agents",
    icon: Bot,
    capability: "agent.use",
  },
  {
    title: "Chat",
    url: "/chat",
    icon: MessageSquare,
    capability: "chat.use",
  },
  {
    title: "Agent Prompts",
    url: "/prompts",
    icon: ScrollText,
    capability: "agent.use",
  },
  {
    title: "Agent Summary Prompts",
    url: "/summary-prompts",
    icon: ScrollText,
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
    title: "Knowledge",
    url: "/knowledge",
    icon: BookOpen,
    capability: "agent.use",
  },
  {
    title: "Users",
    url: "/users",
    icon: Users,
    capability: "users.manage",
  },
]

/**
 * Settings-adjacent pages are grouped under a single collapsible sidebar
 * entry instead of each getting a top-level item, to keep the primary nav
 * short. Same capability-gating rules as allNavItems.
 */
const settingsNavItems = [
  {
    title: "AI Providers",
    url: "/providers",
    icon: Plug,
    capability: "system.providers.manage",
  },
  {
    title: "Models",
    url: "/models",
    icon: Cpu,
    capability: "system.providers.manage",
  },
  {
    title: "Console",
    url: "/console",
    icon: Terminal,
    capability: "agent.use",
  },
  {
    title: "Integrations",
    url: "/integrations",
    icon: Link2,
    capability: "system.integrations.manage",
  },
  {
    title: "MCP Servers",
    url: "/mcp",
    icon: Server,
    capability: "system.mcp.manage",
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
  const settingsItems = isLoading
    ? []
    : settingsNavItems.filter((item) => item.capability === null || hasCapability(item.capability))
  const isSettingsActive = settingsItems.some((item) => location.pathname.startsWith(item.url))

  return (
    <Sidebar collapsible="icon" {...props}>
      <SidebarHeader>
        <AppSidebarHeader />
      </SidebarHeader>
      <SidebarContent>
        <NavMain items={navItems} />
        {settingsItems.length > 0 && (
          <SidebarGroup>
            <SidebarMenu>
              <Collapsible defaultOpen={isSettingsActive} className="group/settings">
                <SidebarMenuItem>
                  <CollapsibleTrigger asChild>
                    <SidebarMenuButton tooltip="Settings" isActive={isSettingsActive}>
                      <Settings />
                      <span>Settings</span>
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
                              <NavLink to={item.url}>
                                <item.icon />
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
            </SidebarMenu>
          </SidebarGroup>
        )}
        {showChatList && <ChatSidebarContent />}
      </SidebarContent>
      <SidebarFooter>
        <NavUser />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
