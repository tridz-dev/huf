import * as React from "react"
import { Bot, Workflow, MessageSquare, Zap, ScrollText, BookOpen, Settings } from "lucide-react"
import { useLocation } from "react-router-dom"

import { NavMain, NavSection } from "@/components/nav-main"
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

const sidebarSections: NavSection[] = [
  {
    label: "Agents",
    items: [
      { title: "Agents", url: "/agents", icon: Bot, capability: "agent.use" },
      { title: "Prompts", url: "/prompts", icon: ScrollText, capability: "agent.use" },
      { title: "Flows", url: "/flows", icon: Workflow, capability: "flows.use" },
    ],
  },
  {
    label: "Activity",
    items: [
      { title: "Chat", url: "/chat", icon: MessageSquare, capability: "chat.use" },
      { title: "Executions", url: "/executions", icon: Zap, capability: "agent.use" },
    ],
  },
  {
    label: "",
    items: [
      {
        title: "Knowledge",
        icon: BookOpen,
        capability: "agent.use",
        items: [
          { title: "Tables", url: "/data", capability: "agent.use" },
          { title: "Documents", url: "/knowledge", capability: "agent.use" },
          { title: "Memory", url: "/memory", capability: "agent.use" },
        ],
      },
      {
        title: "Settings",
        icon: Settings,
        capability: null,
        items: [
          { title: "AI Providers", url: "/providers", capability: null },
          { title: "AI Models", url: "/models", capability: null },
          { title: "MCP Servers", url: "/mcp", capability: null },
          { title: "Users", url: "/users", capability: null },
          { title: "Roles", url: "/roles", capability: null },
        ],
      },
    ],
  },
]

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const location = useLocation()
  const { isMobile } = useSidebar()
  const { hasCapability, isLoading } = usePermissions()
  const isChatPage = location.pathname.startsWith('/chat')

  // Show chat list in sidebar on mobile when on chat page
  const showChatList = isMobile && isChatPage

  // Filter items by capability
  const filteredSections = sidebarSections.map((section) => ({
    ...section,
    items: section.items
      .map(item => {
        // Check main item capability
        const isItemAllowed = isLoading
          ? item.capability === null
          : item.capability === null || (item.capability && hasCapability(item.capability))
        
        if (!isItemAllowed) return null

        // If it has sub-items, filter those too
        if (item.items) {
          const filteredSubItems = item.items.filter(subItem => 
            isLoading
              ? subItem.capability === null
              : subItem.capability === null || (subItem.capability && hasCapability(subItem.capability))
          )
          // If all sub-items are filtered out, don't show the parent if it only acts as a collapsible container
          // But since it might be a valid parent, we will just return it with filtered subItems
          return { ...item, items: filteredSubItems }
        }

        return item
      })
      .filter((item): item is NonNullable<typeof item> => item !== null),
  })).filter(section => section.items.length > 0)

  return (
    <Sidebar collapsible="icon" {...props}>
      <SidebarHeader>
        <AppSidebarHeader />
      </SidebarHeader>
      <SidebarContent>
        <NavMain sections={filteredSections} />
        {showChatList && <ChatSidebarContent />}
      </SidebarContent>
      <SidebarFooter>
        <NavUser />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
