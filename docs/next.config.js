import nextra from 'nextra'

const withNextra = nextra({})

export default withNextra({
  output: 'export',
  basePath: '/assets/agentflo/docs',
  images: {
    unoptimized: true
  },
  trailingSlash: true
})
