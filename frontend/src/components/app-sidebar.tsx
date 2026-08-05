import * as React from "react"
import { ArrowLeft, Home, ChartColumnIncreasing, SquareAsterisk, FileText, Workflow, Database, Plug, MessageSquare, Zap, Server, Users, BookOpen, Link2, Terminal, Settings, LayoutGrid, Brain, Sparkles, Layers, SquareChevronRight, ChevronsLeftRightEllipsis, GlobeLock, Keyboard, SlidersHorizontal } from "lucide-react"
import { useLocation } from "react-router-dom"

import { NavMain } from "@/components/nav-main"
import { NavUser } from "@/components/nav-user"
import { AppSidebarHeader } from "@/components/app-sidebar-header"
import { usePermissions } from "@/contexts/PermissionsContext"
import { fetchDocCountQuiet } from "@/services/utilsApi"
import { doctype } from "@/data/doctypes"
import { ShortcutKey } from "@/components/ui/shortcut-key"
import { useShortcutsHelp } from "@/components/shortcuts/ShortcutsHelpContext"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarHeader,
  SidebarRail,
} from "@/components/ui/sidebar"

/**
 * Each nav item may declare an optional `capability` string or list.
 * If present the item is hidden from users who don't have that capability
 * (a list means any-of: one matching capability is enough).
 * Items with capability === null are always visible (e.g. Dashboard).
 */
export const dashboardNavItems = [
  {
    title: "Hub",
    url: "/",
    icon: Home,
    capability: null,
  },
  {
    title: "Dashboard",
    url: "/dashboard",
    icon: ChartColumnIncreasing,
    capability: null,
  },
]

/**
 * The "Use" side of the platform: end-user HUF Apps discovered from
 * installed provider apps. Build/Operate/People remain the manage side.
 */
export const useNavItems = [
  {
    title: "Apps",
    url: "/apps",
    icon: LayoutGrid,
    capability: "agent.use",
    badge: "Experimental",
  },
  {
    title: "Chat",
    url: "/chat",
    icon: MessageSquare,
    capability: "chat.use",
  },
]

export const buildNavItems = [
  {
    title: "Agents",
    url: "/agents",
    icon: SquareAsterisk,
    capability: "agent.use",
  },
  {
    title: "Prompts",
    url: "/prompts",
    icon: FileText,
    capability: "agent.use",
  },
  {
    title: "Flows",
    url: "/flows",
    icon: Workflow,
    capability: "flows.use",
    badge: "Experimental",
  },
]

/**
 * Knowledge surfaces live in a flat "Know" label group, matching Build and
 * Operate: Tables for structured/relational data, Sources for retrieval
 * knowledge stores backed by any vector/FTS backend (RAG). Future source
 * types (Files, Repos, Drives) nest here as additional items.
 */
export const knowNavItems = [
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
    badge: "Experimental",
  },
  {
    title: "Skills",
    url: "/skills",
    icon: Sparkles,
    capability: "agent.use",
    badge: "Experimental",
  },
]

export const operateNavItems = [
	{
		title: "Executions",
		url: "/executions",
		icon: Zap,
		capability: "agent.use",
		badge: "Experimental",
	},
	{
		title: "Playground",
		url: "/playground",
		icon: Terminal,
		capability: "agent.use",
	},
]

/**
 * Settings is a second-level rail, not an accordion. Opening it replaces the
 * primary navigation so the longer administration list never pushes the main
 * destinations off-screen.
 */
export const settingsNavGroups = [
  {
    label: "General",
    items: [
      { title: "General", url: "/settings/general", icon: SlidersHorizontal, capability: null },
    ],
  },
  {
    label: "Intelligence",
    items: [
      { title: "AI providers", url: "/providers", icon: Plug, capability: "system.providers.manage" },
      { title: "Models", url: "/models", icon: Layers, capability: "system.providers.manage" },
    ],
  },
  {
    label: "Runtime",
    items: [
      { title: "Code execution", url: "/execution-profiles", icon: SquareChevronRight, capability: "agent.use" },
      { title: "SSH connections", url: "/ssh-connections", icon: ChevronsLeftRightEllipsis, capability: "agent.use" },
    ],
  },
  {
    label: "Connectivity",
    items: [
      { title: "Gateways", url: "/gateways", icon: GlobeLock, capability: "system.integrations.manage" },
      { title: "Integrations", url: "/integrations", icon: Link2, capability: "system.integrations.manage" },
      { title: "MCP servers", url: "/mcp", icon: Server, capability: "system.mcp.manage" },
    ],
  },
  {
    label: "Access",
    items: [
      {
        title: "Members",
        url: "/members",
        icon: Users,
        capability: ["users.manage", "roles.manage"],
      },
    ],
  },
]

/**
 * Filters nav items by capability against the current user's granted set.
 * While permissions are loading, only uncapability-gated items are shown so
 * the sidebar (or any other nav consumer, e.g. the command palette) doesn't
 * flash/jump once capabilities resolve.
 */
export function filterItemsByCapability<T extends { capability: string | string[] | null }>(
	items: T[],
	hasCapability: (capability: string) => boolean,
	isLoading: boolean,
) {
	if (isLoading) {
		return items.filter((item) => item.capability === null)
	}
	return items.filter((item) => {
		if (item.capability === null) return true
		const caps = Array.isArray(item.capability) ? item.capability : [item.capability]
		return caps.some((cap) => hasCapability(cap))
	})
}

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const location = useLocation()
  const { hasCapability, isLoading } = usePermissions()
  const [agentCount, setAgentCount] = React.useState<number | undefined>(undefined)
  const { setOpen: setShortcutsHelpOpen } = useShortcutsHelp()

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

	const isPathInItems = (items: { url: string }[]) =>
		items.some(
			(item) =>
				location.pathname === item.url || location.pathname.startsWith(item.url + "/"),
		)

	// While permissions are loading show only uncapability-gated items so the
	// sidebar doesn't flash/jump once capabilities resolve.
	const dashboardItems = filterItemsByCapability(dashboardNavItems, hasCapability, isLoading)
	const useItems = filterItemsByCapability(useNavItems, hasCapability, isLoading)
	const buildItems = filterItemsByCapability(buildNavItems, hasCapability, isLoading).map((item) =>
		item.title === "Agents" ? { ...item, count: agentCount } : item
	)
	const knowledgeItems = filterItemsByCapability(knowNavItems, hasCapability, isLoading)
	const operateItems = filterItemsByCapability(operateNavItems, hasCapability, isLoading)
  const settingsGroups = settingsNavGroups
    .map((group) => ({
      ...group,
      items: filterItemsByCapability(
        group.items as Array<(typeof group.items)[number] & { capability: string | string[] | null }>,
        hasCapability,
        isLoading,
      ),
    }))
    .filter((group) => group.items.length > 0)
  const settingsItems = settingsGroups.flatMap((group) => group.items)
  const settingsActive = isPathInItems(settingsItems)
  const [settingsMode, setSettingsMode] = React.useState(settingsActive)

  React.useEffect(() => {
    if (settingsActive) {
      setSettingsMode(true)
    }
  }, [settingsActive])

  return (
    <Sidebar collapsible="icon" {...props}>
      <SidebarHeader>
        <AppSidebarHeader />
      </SidebarHeader>
      <SidebarContent>
        {settingsMode ? (
          <>
            <SidebarMenu className="px-2">
              <SidebarMenuItem>
                <SidebarMenuButton
                  tooltip="Back to main navigation"
                  onClick={() => setSettingsMode(false)}
                  className="font-medium"
                >
                  <ArrowLeft strokeWidth={1.6} />
                  <span className="font-body text-[13.5px] group-data-[collapsible=icon]:hidden">
                    Settings
                  </span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
            {settingsGroups.map((group) => (
              <NavMain key={group.label} items={group.items} label={group.label} />
            ))}
          </>
        ) : (
          <>
            {dashboardItems.length > 0 && <NavMain items={dashboardItems} />}
            {useItems.length > 0 && <NavMain items={useItems} label="Use" />}
            {buildItems.length > 0 && <NavMain items={buildItems} label="Build" />}
            {knowledgeItems.length > 0 && <NavMain items={knowledgeItems} label="Know" />}
            {operateItems.length > 0 && <NavMain items={operateItems} label="Operate" />}
          </>
        )}
      </SidebarContent>
      <SidebarFooter className="p-0 mb-1 mt-2 border-t border-sidebar-border">
        {!settingsMode && settingsItems.length > 0 && (
          <SidebarMenu className="px-2 pt-2">
            <SidebarMenuItem>
              <SidebarMenuButton tooltip="Settings" onClick={() => setSettingsMode(true)}>
                <Settings strokeWidth={1.6} />
                <span className="font-body text-[13.5px]">Settings</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        )}
        {!settingsMode && (
          <SidebarMenu className="px-2">
            <SidebarMenuItem>
              <SidebarMenuButton
                tooltip="Keyboard shortcuts"
                onClick={() => setShortcutsHelpOpen(true)}
                className="group/shortcut-hint group-data-[collapsible=icon]:justify-center"
              >
                <Keyboard strokeWidth={1.6} />
                <span className="font-body text-[13.5px] flex-1 group-data-[collapsible=icon]:hidden">
                  Keyboard shortcuts
                </span>
                <ShortcutKey
                  size="sm"
                  hoverOnly="shortcut-hint"
                  className="group-data-[collapsible=icon]:hidden"
                >
                  ?
                </ShortcutKey>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        )}
        <NavUser />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
