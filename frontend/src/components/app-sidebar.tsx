import * as React from "react"
import { Home, Bot, Workflow, Database, Plug, MessageSquare, Zap } from "lucide-react"

import { NavMain } from "@/components/nav-main"
import { NavUser } from "@/components/nav-user"
import { AppSidebarHeader } from "@/components/app-sidebar-header"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarRail,
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
    title: "Integrations",
    url: "/integrations",
    icon: Plug,
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
  return (
    <Sidebar collapsible="icon" {...props}>
      <SidebarHeader>
        <AppSidebarHeader />
      </SidebarHeader>
      <SidebarContent>
        <NavMain items={navItems} />
        {/* <NavMain items={systemItems} label="System" /> */}
      </SidebarContent>
      <SidebarFooter>
        <NavUser />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
