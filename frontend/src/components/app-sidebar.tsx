import * as React from "react"
import { Home, Bot, Workflow, Database, Plug, MessageSquare, Zap, Server, ScrollText, Users, BookOpen, Cpu, Link2, Boxes, Terminal, Settings, Shield } from "lucide-react"
import { useLocation } from "react-router-dom"

import { NavMain } from "@/components/nav-main"
import { NavCollapsibleGroup } from "@/components/nav-collapsible"
import { NavUser } from "@/components/nav-user"
import { AppSidebarHeader } from "@/components/app-sidebar-header"
import { usePermissions } from "@/contexts/PermissionsContext"
import { fetchDocCountQuiet } from "@/services/utilsApi"
import { doctype } from "@/data/doctypes"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
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
]

/**
 * Data + retrieval surfaces live under a single collapsible "Knowledge"
 * group, named by user action: Tables for structured/relational data,
 * Documents for unstructured retrieval (RAG).
 */
const knowledgeNavItems = [
  {
    title: "Tables",
    url: "/data",
    icon: Database,
    capability: "agent.view_all",
  },
  {
    title: "Documents",
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

/**
 * Settings-adjacent pages are grouped under a single collapsible sidebar
 * entry instead of each getting a top-level item, to keep the primary nav
 * short. User management lives here too — it's an admin task, not a daily
 * destination. Same capability-gating rules as allNavItems.
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
    title: "Integration Services",
    url: "/integration-services",
    icon: Boxes,
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
  {
    title: "Users",
    url: "/users",
    icon: Users,
    capability: "users.manage",
  },
]

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const location = useLocation()
  const { hasCapability, isLoading } = usePermissions()
  const [agentCount, setAgentCount] = React.useState<number | undefined>(undefined)

  React.useEffect(() => {
    let cancelled = false
    fetchDocCountQuiet(doctype.Agent).then((count) => {
      if (!cancelled) {
        setAgentCount(count)
      }
    })
    return () => {
      cancelled = true
    }
  }, [])

	const filterItemsByCapability = <T extends { capability: string | null }>(items: T[]) => {
		if (isLoading) {
			return items.filter((item) => item.capability === null)
		}
		return items.filter(
			(item) => item.capability === null || (item.capability && hasCapability(item.capability)),
		)
	}

	const isPathInItems = (items: { url: string }[]) =>
		items.some(
			(item) =>
				location.pathname === item.url || location.pathname.startsWith(item.url + "/"),
		)

	// While permissions are loading show only uncapability-gated items so the
	// sidebar doesn't flash/jump once capabilities resolve.
	const dashboardItems = filterItemsByCapability(dashboardNavItems)
	const buildItems = filterItemsByCapability(buildNavItems).map((item) =>
		item.title === "Agents" ? { ...item, count: agentCount } : item
	)
	const knowledgeItems = filterItemsByCapability(knowledgeNavItems)
	const operateItems = filterItemsByCapability(operateNavItems)
  const settingsItems = isLoading
    ? []
    : settingsNavItems.filter((item) => item.capability === null || hasCapability(item.capability))

  // Accordion: at most one collapsible group open at a time. The group
  // containing the active route auto-opens on navigation.
  const [openGroup, setOpenGroup] = React.useState<string | null>(null)
  const knowledgeActive = isPathInItems(knowledgeItems)
  const settingsActive = isPathInItems(settingsItems)

  React.useEffect(() => {
    if (knowledgeActive) {
      setOpenGroup("knowledge")
    } else if (settingsActive) {
      setOpenGroup("settings")
    }
  }, [knowledgeActive, settingsActive])

  return (
    <Sidebar collapsible="icon" {...props}>
      <SidebarHeader>
        <AppSidebarHeader />
      </SidebarHeader>
      <SidebarContent>
			{dashboardItems.length > 0 && <NavMain items={dashboardItems} />}
			{buildItems.length > 0 && <NavMain items={buildItems} label="Build" />}
			{knowledgeItems.length > 0 && (
			  <NavCollapsibleGroup
			    title="Knowledge"
			    icon={BookOpen}
			    items={knowledgeItems}
			    open={openGroup === "knowledge"}
			    onOpenChange={(open) => setOpenGroup(open ? "knowledge" : null)}
			  />
			)}
			{operateItems.length > 0 && <NavMain items={operateItems} label="Operate" />}
			{settingsItems.length > 0 && (
			  <NavCollapsibleGroup
			    title="Settings"
			    icon={Settings}
			    items={settingsItems}
			    open={openGroup === "settings"}
			    onOpenChange={(open) => setOpenGroup(open ? "settings" : null)}
			  />
			)}
      </SidebarContent>
      <SidebarFooter className="p-0 mb-1 mt-2 border-t border-sidebar-border">
        <NavUser />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
