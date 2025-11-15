# Huf Documentation

This directory contains the Nextra-based documentation for Huf.

## Development

To run the documentation locally:

```bash
npm install
npm run dev
```

The documentation will be available at `http://localhost:3000`.

## Building

To build the documentation for production:

```bash
npm run build
npm start
```

## Structure

- `app/` - Next.js app directory
  - `page.mdx` - Homepage
  - `docs/` - Documentation pages
    - `installation/` - Installation guide
    - `quick-start/` - Quick start guide
    - `agents/` - Agents documentation
    - `tools/` - Tools documentation
    - `conversations/` - Conversations documentation
    - `monitoring/` - Monitoring documentation
    - `development/` - Development guide
- `theme.config.jsx` - Nextra theme configuration
- `next.config.js` - Next.js configuration

## Content Guidelines

- Focus on users, not developers (except in Development section)
- Use clear, simple language
- Provide step-by-step instructions
- Include examples and use cases
- Reference Frappe documentation where appropriate
