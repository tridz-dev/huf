import nextra from 'nextra'

const withNextra = nextra({})

// For GitHub Pages, use repo name as basePath
// For Frappe, use /assets/agentflo/docs
// Default to GitHub Pages if GITHUB_PAGES env var is set
const basePath = process.env.GITHUB_PAGES === 'true' 
  ? '/agent_flo' 
  : '/assets/agentflo/docs'

export default withNextra({
  output: 'export',
  basePath,
  images: {
    unoptimized: true
  },
  trailingSlash: true
})
