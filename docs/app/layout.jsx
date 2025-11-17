import { Footer, Layout, Navbar } from 'nextra-theme-docs'
import { Head } from 'nextra/components'
import { getPageMap } from 'nextra/page-map'
import 'nextra-theme-docs/style.css'

export const metadata = {
  title: 'Huf Documentation',
  description: 'Documentation for Huf - AI agents for Frappe Framework'
}

const navbar = (
  <Navbar
    logo={
      <>
        <span style={{ fontWeight: 800, fontSize: '1.2em' }}>Huf</span>
      </>
    }
    projectLink="https://github.com/Tridz/agentflo"
  />
)

const footer = (
  <Footer>
    MIT {new Date().getFullYear()} © Huf. Built with{' '}
    <a href="https://nextra.site" target="_blank" rel="noreferrer">
      Nextra
    </a>
    .
  </Footer>
)

function sortPageMap(pageMap) {
  const order = [
    'quick-start',
    'installation',
    'concepts',
    'tools',
    'use-cases',
    'examples',
    'guides',
    'development'
  ]
  
  return pageMap.map(item => {
    if (item.children) {
      return {
        ...item,
        children: item.children.slice().sort((a, b) => {
          const indexA = order.indexOf(a.name)
          const indexB = order.indexOf(b.name)
          if (indexA === -1 && indexB === -1) return 0
          if (indexA === -1) return 1
          if (indexB === -1) return -1
          return indexA - indexB
        }).map(child => child.children ? { ...child, children: child.children } : child)
      }
    }
    return item
  })
}

export default async function RootLayout({ children }) {
  const pageMap = await getPageMap()
  const sortedPageMap = sortPageMap(pageMap)
  
  return (
    <html lang="en" dir="ltr" suppressHydrationWarning>
      <Head />
      <body>
        <Layout
          navbar={navbar}
          pageMap={sortedPageMap}
          docsRepositoryBase="https://github.com/Tridz/agentflo/tree/main/docs"
          footer={footer}
        >
          {children}
        </Layout>
      </body>
    </html>
  )
}
