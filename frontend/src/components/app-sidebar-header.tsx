import {
  SidebarMenu,
  SidebarMenuItem,
} from "@/components/ui/sidebar"

export function AppSidebarHeader() {
  return (
    <SidebarMenu>
      <SidebarMenuItem>
        {/*
          Expanded: HUF wordmark + signal square + "AI Platform" eyebrow.
          Collapsed (spec §11): the mark becomes a 26x26 accent tile with a
          7px radius, centred in the 64px rail with 10px below it.
        */}
        <div className="flex items-center gap-2 px-2 py-3 group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-0 group-data-[collapsible=icon]:pb-[10px] group-data-[collapsible=icon]:pt-3">
          <span className="font-display font-bold text-[22px] uppercase leading-none text-ink tracking-tight group-data-[collapsible=icon]:hidden">
            HUF
          </span>
          <span className="inline-block h-2 w-2 flex-shrink-0 bg-signal group-data-[collapsible=icon]:h-[26px] group-data-[collapsible=icon]:w-[26px] group-data-[collapsible=icon]:rounded-[7px]" />
          <span className="font-mono text-[10px] text-steel-soft uppercase tracking-widest group-data-[collapsible=icon]:hidden">
            AI Platform
          </span>
        </div>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}
