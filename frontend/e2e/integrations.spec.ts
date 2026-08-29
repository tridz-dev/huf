import { test, expect } from '@playwright/test';
import { goto, waitForContent, mockOfflineApis } from './helpers';

test.describe('Integrations, Knowledge & MCP', () => {
  test.beforeEach(async ({ page }) => {
    await mockOfflineApis(page);
  });

  test('integrations page renders', async ({ page }) => {
    await goto(page, '/integrations');
    await waitForContent(page);
    // IntegrationSettingsListingPage has no PageFrame title/subtitle band —
    // its filter bar's search input is the reliable, unambiguous marker
    // that this page (kind: 'integrations') rendered.
    await expect(page.getByPlaceholder('Search integrations...')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'No integrations' })).toBeVisible();
  });

  test('integration services page renders', async ({ page }) => {
    await goto(page, '/integration-services');
    await waitForContent(page);
    await expect(page.getByPlaceholder('Search services...')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'No integration services' })).toBeVisible();
  });

  test('knowledge sources page renders', async ({ page }) => {
    await goto(page, '/knowledge');
    await waitForContent(page);
    await expect(page.getByPlaceholder('Search knowledge sources...')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'No knowledge sources' })).toBeVisible();
  });

  test('mcp servers page renders', async ({ page }) => {
    await goto(page, '/mcp');
    await waitForContent(page);
    // "MCP servers" (page title, exact) and "No MCP servers" (empty-state
    // heading) both match a loose heading query — pin the page title.
    await expect(page.getByRole('heading', { name: 'MCP servers', exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'No MCP servers', exact: true })).toBeVisible();
  });
});
