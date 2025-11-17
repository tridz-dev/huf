# GitHub Pages Setup

This documentation is automatically deployed to GitHub Pages when changes are pushed to the `main` or `master` branch.

## How It Works

1. **GitHub Actions Workflow**: `.github/workflows/pages.yml` automatically builds and deploys the docs
2. **Build Process**: Uses `npm run build:pages` which sets the correct `basePath` for GitHub Pages
3. **Deployment**: Built files are deployed to the `gh-pages` branch automatically

## Enabling GitHub Pages

To enable GitHub Pages for this repository:

1. Go to **Settings** → **Pages** in your GitHub repository
2. Under **Source**, select **GitHub Actions**
3. The workflow will automatically deploy on the next push to `main`/`master`

## Documentation URLs

- **GitHub Pages**: https://tridz-dev.github.io/agent_flo/
- **Frappe Site**: `/docs` (when installed on a Frappe site)

## Build Scripts

- `npm run build` - Builds for Frappe (copies to `public/docs/` and `www/docs.html`)
- `npm run build:pages` - Builds for GitHub Pages (uses `/agent_flo` as basePath)

## Manual Deployment

If you need to deploy manually:

```bash
cd docs
npm run build:pages
# The output will be in docs/out/
# You can manually copy this to gh-pages branch if needed
```

## Troubleshooting

- **404 errors**: Make sure GitHub Pages is enabled and set to use GitHub Actions
- **Wrong basePath**: Check that `GITHUB_PAGES=true` is set when building
- **Build fails**: Check GitHub Actions logs in the repository's Actions tab

