import * as React from "react"
import { Home, Bot, Workflow, Database, Plug, MessageSquare, Zap, Server } from "lucide-react"
import { useLocation } from "react-router-dom"

import { NavMain } from "@/components/nav-main"
import { NavUser } from "@/components/nav-user"
import { AppSidebarHeader } from "@/components/app-sidebar-header"
import { ChatSidebarContent } from "@/components/chat/ChatSidebarContent"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarRail,
  useSidebar,
} from "@/components/ui/sidebar"

const navItems = [
  {
    title: "Dashboard",
    url: "/",
    icon: Home,
  },
  {
    title: "Agents",
    url: "/agents",
    icon: Bot,
  },
  {
    title: "Chat",
    url: "/chat",
    icon: MessageSquare,
  },
  {
    title: "Executions",
    url: "/executions",
    icon: Zap,
  },
  {
    title: "Flows",
    url: "/flows",
    icon: Workflow,
  },
  {
    title: "Data",
    url: "/data",
    icon: Database,
  },
  {
    title: "AI Providers",
    url: "/providers",
    icon: Plug,
  },
  {
    title: "MCP Servers",
    url: "/mcp",
    icon: Server,
  },
]

// const systemItems = [
//   {
//     title: "Settings",
//     url: "/settings",
//     icon: Settings,
//   },
//   {
//     title: "Help",
//     url: "/help",
//     icon: HelpCircle,
//   },
// ]

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const location = useLocation()
  const { isMobile } = useSidebar()
  const isChatPage = location.pathname.startsWith('/chat')
  
  // Show chat list in sidebar on mobile when on chat page
  const showChatList = isMobile && isChatPage

  return (
    <Sidebar collapsible="icon" {...props}>
      <SidebarHeader>
        <AppSidebarHeader />
      </SidebarHeader>
      <SidebarContent>
        <NavMain items={navItems} />
        {showChatList && <ChatSidebarContent />}
        {/* <NavMain items={systemItems} label="System" /> */}
      </SidebarContent>
      <SidebarFooter>
        <NavUser />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
