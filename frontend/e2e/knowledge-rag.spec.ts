import { test, expect } from '@playwright/test';

// Covers Phase 4.2 (knowledge/RAG flow) from docs/TESTING_PLAN.md.
const TEST_SOURCE_NAME = `_e2e-test-source-${Date.now()}`;

test.describe('Knowledge source flow', () => {
  test('knowledge sources list renders', async ({ page }) => {
    await page.goto('knowledge');
    await expect(page.getByText('Manage knowledge sources for your AI agents')).toBeVisible();
  });

  test('creating a knowledge source with required fields succeeds', async ({ page }) => {
    await page.goto('knowledge');
    await page.getByRole('button', { name: 'New Knowledge Source' }).click();

    await expect(page).toHaveURL(/\/huf\/knowledge\/new/);

    // GeneralTab.tsx: source_name is the only strictly required field on
    // creation; knowledge_type/scope/storage_mode carry select defaults.
    await page.getByPlaceholder('my-knowledge-source').fill(TEST_SOURCE_NAME);

    await page.getByRole('button', { name: /^Save$/i }).or(page.getByRole('button', { name: /^Create$/i })).click();

    // On success the form navigates off /knowledge/new to the saved
    // source's detail page (URL now has a real id, not "new").
    await page.waitForURL(/\/huf\/knowledge\/(?!new)[^/]+$/, { timeout: 10000 });
    await expect(page.getByText(TEST_SOURCE_NAME)).toBeVisible();
  });
});
