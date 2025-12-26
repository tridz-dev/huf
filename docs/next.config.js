import nextra from 'nextra'

const withNextra = nextra({})

// For GitHub Pages, use repo name as basePath
// For Frappe, use /huf/docs (mapped via website_route_rules in hooks.py)
// For local serving, use no basePath/assetPrefix
// Default to GitHub Pages if GITHUB_PAGES env var is set
// Extract repository name from GITHUB_REPOSITORY (format: owner/repo-name)
// const getGitHubPagesBasePath = () => {
//   return ""
//   if (process.env.GITHUB_REPOSITORY) {
//     const repoName = process.env.GITHUB_REPOSITORY.split('/')[1]
//     return `/${repoName}`
//   }
//   // Fallback - update this to match your actual repository name
//   return '/agent_flo'
// }

// LOCAL_SERVE=true disables basePath/assetPrefix for direct serving of out folder
const isLocalServe = process.env.LOCAL_SERVE === 'true' || process.env.NODE_ENV === 'development'

const basePath = isLocalServe
  ? ''
  : process.env.GITHUB_PAGES === 'true' 
    ? ''
    : '/huf/docs'

// For Frappe, assets are served from /assets/huf/docs but pages are at /huf/docs
// So we use assetPrefix to point assets to the correct location
// For local serving, no assetPrefix needed
const assetPrefix = isLocalServe
  ? undefined
  : process.env.GITHUB_PAGES === 'true'
    ? undefined
    : '/assets/huf/'

export default withNextra({
  output: 'export',
  basePath,
  assetPrefix,
  images: {
    unoptimized: true
  },
  trailingSlash: true
})
