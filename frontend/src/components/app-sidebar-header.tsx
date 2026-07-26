import {
  SidebarMenu,
  SidebarMenuItem,
} from "@/components/ui/sidebar"

export function AppSidebarHeader() {
  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <div className="flex items-center gap-2 px-2 py-3">
          {/* HUF wordmark + signal square */}
          <span className="font-display font-bold text-[22px] uppercase leading-none text-ink tracking-tight group-data-[collapsible=icon]:hidden">
            HUF
          </span>
          <span className="inline-block w-2 h-2 bg-signal flex-shrink-0" />
          <span className="font-mono text-[10px] text-steel-soft uppercase tracking-widest group-data-[collapsible=icon]:hidden">
            AI Platform
          </span>
        </div>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}
