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
          <svg 
            xmlns="http://www.w3.org/2000/svg" 
            viewBox="726 420 468 240" 
            className="h-[18px] w-auto text-ink group-data-[collapsible=icon]:hidden"
            fill="currentColor"
          >
            <path d="M1064.37 590.387C1064.37 607.132 1050.8 620.707 1034.05 620.707H1025.1V660H948.299C924.856 660 905.85 640.995 905.85 617.552V494.866H945.267V620.584H1024.95V494.865H1064.37V590.387ZM1193.11 459.567H1149.69V494.798H1181.05V525.119H1149.69V629.278C1149.69 646.023 1136.12 659.598 1119.38 659.598H1110.28V525.119H1090.39V494.798H1110.28V462.6C1110.28 439.156 1129.28 420.151 1152.73 420.151H1193.11V459.567ZM766.305 494.462H842.96C866.404 494.462 885.409 513.467 885.409 536.911V659.597H845.993V533.879H766.305V659.597H726.888V564.075C726.888 547.33 740.464 533.755 757.209 533.755H766.161V494.866H726.888V420H766.305V494.462Z" />
          </svg>
          <span className="inline-block h-2 w-2 flex-shrink-0 bg-signal group-data-[collapsible=icon]:h-[26px] group-data-[collapsible=icon]:w-[26px] group-data-[collapsible=icon]:rounded-[7px]" />
          <span className="font-mono text-[10px] text-steel-soft uppercase tracking-widest group-data-[collapsible=icon]:hidden">
            AI platform
          </span>
        </div>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}
