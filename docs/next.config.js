import nextra from 'nextra'

const withNextra = nextra({})

// For GitHub Pages, use repo name as basePath
// For Frappe, use /huf/docs (mapped via website_route_rules in hooks.py)
// Default to GitHub Pages if GITHUB_PAGES env var is set
const basePath = process.env.GITHUB_PAGES === 'true' 
  ? '/agent_flo' 
  : '/huf/docs'

// For Frappe, assets are served from /assets/agentflo/docs but pages are at /huf/docs
// So we use assetPrefix to point assets to the correct location
const assetPrefix = process.env.GITHUB_PAGES === 'true'
  ? undefined
  : '/assets/agentflo/docs'

export default withNextra({
  output: 'export',
  basePath,
  assetPrefix,
  images: {
    unoptimized: true
  },
  trailingSlash: true
})
