import * as React from "react"
import { Home, Bot, Workflow, Database, Plug, MessageSquare, Zap, Server, ScrollText, Users, BookOpen, Cpu, Link2, Boxes, Terminal, Settings, ChevronRight, Shield } from "lucide-react"
import { NavLink, useLocation } from "react-router-dom"

import { NavMain } from "@/components/nav-main"
import { NavUser } from "@/components/nav-user"
import { AppSidebarHeader } from "@/components/app-sidebar-header"
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
} from "@/components/ui/sidebar"

/**
 * Each nav item may declare an optional `capability` string.
 * If present the item is hidden from users who don't have that capability.
 * Items with capability === null are always visible (e.g. Dashboard).
 */
const dashboardNavItems = [
  {
    title: "Dashboard",
    url: "/",
    icon: Home,
    capability: null,
  },
]

const buildNavItems = [
  {
    title: "Agents",
    url: "/agents",
    icon: Bot,
    capability: "agent.use",
  },
  {
    title: "Agent Prompts",
    url: "/prompts",
    icon: ScrollText,
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
]

const operateNavItems = [
	{
		title: "Chat",
		url: "/chat",
		icon: MessageSquare,
		capability: "chat.use",
	},
	{
		title: "Executions",
		url: "/executions",
		icon: Zap,
		capability: "agent.use",
	},
	{
		title: "Artifacts",
		url: "/artifacts",
		icon: Boxes,
		capability: "agent.view_all",
	},
]

const peopleNavItems = [
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
		title: "Agent Summary Prompts",
		url: "/summary-prompts",
		icon: ScrollText,
		capability: "agent.use",
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
  {
    title: "Roles",
    url: "/roles",
    icon: Shield,
    capability: "roles.manage",
  },
]

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const location = useLocation()
  const { hasCapability, isLoading } = usePermissions()

	const filterItemsByCapability = <T extends { capability: string | null }>(items: T[]) => {
		if (isLoading) {
			return items.filter((item) => item.capability === null)
		}
		return items.filter(
			(item) => item.capability === null || (item.capability && hasCapability(item.capability)),
		)
	}

	// While permissions are loading show only uncapability-gated items so the
	// sidebar doesn't flash/jump once capabilities resolve.
	const dashboardItems = filterItemsByCapability(dashboardNavItems)
	const buildItems = filterItemsByCapability(buildNavItems)
	const operateItems = filterItemsByCapability(operateNavItems)
	const peopleItems = filterItemsByCapability(peopleNavItems)
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
			{dashboardItems.length > 0 && <NavMain items={dashboardItems} />}
			{buildItems.length > 0 && <NavMain items={buildItems} label="Build" />}
			{operateItems.length > 0 && <NavMain items={operateItems} label="Operate" />}
			{peopleItems.length > 0 && <NavMain items={peopleItems} label="People" />}
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
      </SidebarContent>
      <SidebarFooter>
        <NavUser />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
