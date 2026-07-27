import * as React from "react"
import { Home, LayoutDashboard, Bot, Workflow, Database, Plug, MessageSquare, Zap, Server, ScrollText, Users, BookOpen, Cpu, Link2, Boxes, Terminal, Settings, Shield, LayoutGrid, Brain, Sparkles } from "lucide-react"
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
 * Each nav item may declare an optional `capability` string or list.
 * If present the item is hidden from users who don't have that capability
 * (a list means any-of: one matching capability is enough).
 * Items with capability === null are always visible (e.g. Dashboard).
 */
const dashboardNavItems = [
  {
    title: "Hub",
    url: "/",
    icon: Home,
    capability: null,
  },
  {
    title: "Dashboard",
    url: "/dashboard",
    icon: LayoutDashboard,
    capability: null,
  },
]

/**
 * The "Use" side of the platform: end-user HUF Apps discovered from
 * installed provider apps. Build/Operate/People remain the manage side.
 */
const useNavItems = [
  {
    title: "Apps",
    url: "/apps",
    icon: LayoutGrid,
    capability: "agent.use",
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
 * Knowledge surfaces live in a flat "Know" label group, matching Build and
 * Operate: Tables for structured/relational data, Sources for retrieval
 * knowledge stores backed by any vector/FTS backend (RAG). Future source
 * types (Files, Repos, Drives) nest here as additional items.
 */
const knowNavItems = [
  {
    title: "Tables",
    url: "/data",
    icon: Database,
    capability: [
      "data.tables.manage",
      "data.records.view_own",
      "data.records.view_all",
    ],
  },
  {
    title: "Sources",
    url: "/knowledge",
    icon: BookOpen,
    capability: "agent.use",
  },
  {
    title: "Memory",
    url: "/memory",
    icon: Brain,
    capability: "agent.use",
  },
  {
    title: "Skills",
    url: "/skills",
    icon: Sparkles,
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
		title: "Execution Profiles",
		url: "/execution-profiles",
		icon: Shield,
		capability: "agent.use",
	},
	{
		title: "SSH Connections",
		url: "/ssh-connections",
		icon: Terminal,
		capability: "agent.use",
	},
  {
    title: "Console",
    url: "/console",
    icon: Terminal,
    capability: "agent.use",
  },
  // TODO(#473-followup): Gateways navigation is hidden while the feature is
  // incomplete (no live provider adapters, no in-app connection form). Restore
  // once the items in docs/gateway-todo.md are resolved.
  // {
  //   title: "Gateways",
  //   url: "/gateways",
  //   icon: MessageSquare,
  //   capability: "system.integrations.manage",
  // },
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

	const filterItemsByCapability = <T extends { capability: string | string[] | null }>(items: T[]) => {
		if (isLoading) {
			return items.filter((item) => item.capability === null)
		}
		return items.filter((item) => {
			if (item.capability === null) return true
			const caps = Array.isArray(item.capability) ? item.capability : [item.capability]
			return caps.some((cap) => hasCapability(cap))
		})
	}

	const isPathInItems = (items: { url: string }[]) =>
		items.some(
			(item) =>
				location.pathname === item.url || location.pathname.startsWith(item.url + "/"),
		)

	// While permissions are loading show only uncapability-gated items so the
	// sidebar doesn't flash/jump once capabilities resolve.
	const dashboardItems = filterItemsByCapability(dashboardNavItems)
	const useItems = filterItemsByCapability(useNavItems)
	const buildItems = filterItemsByCapability(buildNavItems).map((item) =>
		item.title === "Agents" ? { ...item, count: agentCount } : item
	)
	const knowledgeItems = filterItemsByCapability(knowNavItems)
	const operateItems = filterItemsByCapability(operateNavItems)
  const settingsItems = isLoading
    ? []
    : settingsNavItems.filter((item) => item.capability === null || hasCapability(item.capability))

  // Settings is the only collapsible group; its open state is owned here so
  // the active route auto-opens it on navigation.
  const settingsActive = isPathInItems(settingsItems)
  const [settingsOpen, setSettingsOpen] = React.useState(settingsActive)

  React.useEffect(() => {
    if (settingsActive) {
      setSettingsOpen(true)
    }
  }, [settingsActive])

  return (
    <Sidebar collapsible="icon" {...props}>
      <SidebarHeader>
        <AppSidebarHeader />
      </SidebarHeader>
      <SidebarContent>
			{dashboardItems.length > 0 && <NavMain items={dashboardItems} />}
			{useItems.length > 0 && <NavMain items={useItems} label="Use" />}
			{buildItems.length > 0 && <NavMain items={buildItems} label="Build" />}
			{knowledgeItems.length > 0 && <NavMain items={knowledgeItems} label="Know" />}
			{operateItems.length > 0 && <NavMain items={operateItems} label="Operate" />}
			{settingsItems.length > 0 && (
			  <NavCollapsibleGroup
			    title="Settings"
			    icon={Settings}
			    items={settingsItems}
			    open={settingsOpen}
			    onOpenChange={setSettingsOpen}
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
