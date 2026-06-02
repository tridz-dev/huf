import * as React from "react"
import { NavLink } from "react-router-dom"

export interface InnerSidebarSection {
  label: string
  items: {
    title: string
    url: string
    icon?: React.ElementType
    exact?: boolean
  }[]
}

interface InnerSidebarLayoutProps {
  sections: InnerSidebarSection[]
  children: React.ReactNode
}

export function InnerSidebarLayout({ sections, children }: InnerSidebarLayoutProps) {
  return (
    <div className="flex h-full w-full overflow-hidden bg-background">
      {/* Inner Sidebar */}
      <aside className="w-[220px] flex-shrink-0 border-r border-border bg-card flex flex-col py-4">
        <div className="flex-1 overflow-y-auto px-3">
          {sections.map((section, idx) => (
            <div key={idx} className="mb-6 last:mb-0">
              <h4 className="mb-2 px-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                {section.label}
              </h4>
              <nav className="flex flex-col gap-1">
                {section.items.map((item) => {
                  const Icon = item.icon
                  return (
                    <NavLink
                      key={item.title}
                      to={item.url}
                      end={item.exact}
                      className={({ isActive }) =>
                        `flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors ${
                          isActive
                            ? "bg-secondary text-secondary-foreground font-medium"
                            : "text-muted-foreground hover:bg-secondary/50 hover:text-primary"
                        }`
                      }
                    >
                      {({ isActive }) => (
                        <>
                          {Icon && (
                            <Icon
                              className={`h-4 w-4 ${isActive ? "text-primary" : "text-muted-foreground"}`}
                            />
                          )}
                          <span>{item.title}</span>
                        </>
                      )}
                    </NavLink>
                  )
                })}
              </nav>
            </div>
          ))}
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 overflow-hidden">
        {children}
      </main>
    </div>
  )
}
