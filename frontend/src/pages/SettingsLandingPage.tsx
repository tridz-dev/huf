import { Plug, Cpu, Server, Users, Shield } from "lucide-react"
import { Outlet } from "react-router-dom"
import { InnerSidebarLayout } from "../components/layout/InnerSidebarLayout"

const settingsSections = [
  {
    label: "AI",
    items: [
      { title: "AI Providers", url: "/providers", icon: Plug, exact: false },
      { title: "AI Models", url: "/models", icon: Cpu, exact: false },
    ]
  },
  {
    label: "Integrations",
    items: [
      { title: "MCP Servers", url: "/mcp", icon: Server, exact: false },
    ]
  },
  {
    label: "System",
    items: [
      { title: "Users", url: "/users", icon: Users, exact: false },
      { title: "Roles", url: "/roles", icon: Shield, exact: false },
    ]
  }
]

export default function SettingsLandingPage() {
  return (
    <InnerSidebarLayout sections={settingsSections}>
      <Outlet />
    </InnerSidebarLayout>
  )
}
