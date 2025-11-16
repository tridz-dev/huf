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

export default async function RootLayout({ children }) {
  return (
    <html lang="en" dir="ltr" suppressHydrationWarning>
      <Head />
      <body>
        <Layout
          navbar={navbar}
          pageMap={await getPageMap()}
          docsRepositoryBase="https://github.com/Tridz/agentflo/tree/main/docs"
          footer={footer}
        >
          {children}
        </Layout>
      </body>
    </html>
  )
}
