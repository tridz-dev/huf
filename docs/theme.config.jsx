// This file is kept for Nextra compatibility but configuration is in app/layout.jsx
export default {
  logo: <span style={{ fontWeight: 800 }}>Huf</span>,
  project: {
    link: 'https://github.com/tridz-dev/agent_flo'
  },
  docsRepositoryBase: 'https://github.com/tridz-dev/agent_flo/tree/main/docs',
  search: {
    placeholder: 'Search documentation...'
  },
  sidebar: {
    defaultMenuCollapseLevel: 1,
    autoCollapse: true
  },
  toc: {
    float: true
  },
  editLink: {
    text: 'Edit this page on GitHub →'
  },
  feedback: {
    content: 'Question? Give us feedback →',
    labels: 'feedback'
  },
  navigation: {
    prev: true,
    next: true
  },
  footer: {
    text: `AGPL ${new Date().getFullYear()} © Tridz Technologies Ltd.`
  }
}
