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
      { title: "Knowledge", url: "/knowledge", icon: BookOpen, capability: "agent.use" },
      { title: "Settings", url: "/settings", icon: Settings, capability: null },
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
    items: isLoading
      ? section.items.filter((item) => item.capability === null)
      : section.items.filter((item) => item.capability === null || (item.capability && hasCapability(item.capability))),
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
