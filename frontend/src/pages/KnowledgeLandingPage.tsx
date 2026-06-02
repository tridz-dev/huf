import { BookOpen, Database } from "lucide-react"
import { Outlet } from "react-router-dom"
import { InnerSidebarLayout } from "../components/layout/InnerSidebarLayout"

const knowledgeSections = [
  {
    label: "Knowledge",
    items: [
      { title: "Sources", url: "/knowledge", icon: BookOpen, exact: true },
    ]
  },
  {
    label: "Data",
    items: [
      { title: "Tables", url: "/data", icon: Database, exact: false },
    ]
  },
]

export default function KnowledgeLandingPage() {
  return (
    <InnerSidebarLayout sections={knowledgeSections}>
      <Outlet />
    </InnerSidebarLayout>
  )
}
