import * as React from "react"
import { ArrowLeft, Home, ChartColumnIncreasing, SquareAsterisk, FileText, Workflow, Database, Layers, MessageSquare, Zap, Server, Users, BookOpen, Link2, Terminal, Settings, LayoutGrid, Brain, Sparkles, SquareChevronRight, ChevronsLeftRightEllipsis, GlobeLock, Keyboard, SlidersHorizontal, type LucideIcon } from "lucide-react"
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
]

/**
 * The "Use" side of the platform: end-user HUF Apps discovered from
 * installed provider apps. Build/Library/Monitor remain the manage side.
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
    title: "Flows",
    url: "/flows",
    icon: Workflow,
    capability: "flows.use",
    badge: "Experimental",
  },
  {
    title: "Intelligence",
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
  {
    title: "Automations",
    url: "/automations",
    icon: Zap,
    capability: "agent.use",
    badge: "Experimental",
  },
]

/**
 * Library surfaces live in a flat "Library" label group: Prompts for reusable
 * prompt templates, Sources for retrieval knowledge stores backed by any
 * vector/FTS backend (RAG), Tables for structured/relational data.
 */
export const libraryNavItems = [
  {
    title: "Prompts",
    url: "/prompts",
    icon: FileText,
    capability: "agent.use",
  },
  {
    title: "Sources",
    url: "/knowledge",
    icon: BookOpen,
    capability: "agent.use",
  },
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
]

export const operateNavItems = [
	{
		title: "Dashboard",
		url: "/dashboard",
		icon: ChartColumnIncreasing,
		capability: null,
	},
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
export const settingsNavGroups: Array<{ label?: string; items: Array<{ title: string; url: string; icon: LucideIcon; capability: string | string[] | null }> }> = [
  {
    items: [
      { title: "General", url: "/settings/general", icon: SlidersHorizontal, capability: null },
      { title: "AI providers & models", url: "/providers", icon: Layers, capability: "system.providers.manage" },
      { title: "MCP servers", url: "/mcp", icon: Server, capability: "system.mcp.manage" },
      { title: "Gateways", url: "/gateways", icon: GlobeLock, capability: "system.integrations.manage" },
      { title: "Integrations", url: "/integrations", icon: Link2, capability: "system.integrations.manage" },
      { title: "Code execution", url: "/execution-profiles", icon: SquareChevronRight, capability: "agent.use" },
      { title: "SSH connections", url: "/ssh-connections", icon: ChevronsLeftRightEllipsis, capability: "agent.use" },
      {
        title: "Members",
        url: "/members",
        icon: Users,
        capability: ["users.manage", "roles.manage"],
      },
      { title: "Developer", url: "/settings/developer", icon: Terminal, capability: null },
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
	const libraryItems = filterItemsByCapability(libraryNavItems, hasCapability, isLoading)
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
              <NavMain key={group.label ?? "settings"} items={group.items} label={group.label} />
            ))}
          </>
        ) : (
          <>
            {dashboardItems.length > 0 && <NavMain items={dashboardItems} />}
            {useItems.length > 0 && <NavMain items={useItems} />}
            {buildItems.length > 0 && <NavMain items={buildItems} label="Build" />}
            {libraryItems.length > 0 && <NavMain items={libraryItems} label="Library" />}
            {operateItems.length > 0 && <NavMain items={operateItems} label="Monitor" />}
          </>
        )}
      </SidebarContent>
      <SidebarFooter className="p-0 mb-1 mt-2 border-t border-sidebar-border">
        {!settingsMode && settingsItems.length > 0 && (
          <SidebarMenu className="px-2 pt-2">
            <SidebarMenuItem>
              <SidebarMenuButton tooltip="Settings" onClick={() => setSettingsMode(true)}>
                <Settings strokeWidth={1.6} />
                <span className="font-body text-[13.5px] group-data-[collapsible=icon]:hidden">Settings</span>
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
