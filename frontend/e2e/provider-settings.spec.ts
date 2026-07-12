import { test, expect } from '@playwright/test';

// Covers Phase 4.3 (provider/model settings flow) and 4.5 (auth-failure
// error path) from docs/TESTING_PLAN.md. Uses a throwaway provider name per
// run so repeated CI executions don't collide on the unique provider_name
// constraint (see huf/huf/doctype/ai_provider/ai_provider.json).
const TEST_PROVIDER_NAME = `_E2E Test Provider ${Date.now()}`;

test.describe('AI Provider settings', () => {
  test('creating a provider with required fields succeeds', async ({ page }) => {
    await page.goto('providers');
    await expect(page.getByText('Connect AI providers and external services')).toBeVisible();

    await page.getByRole('button', { name: 'Add Provider' }).click();
    await expect(page.getByRole('heading', { name: 'Add Provider' }).or(page.getByText('Add Provider'))).toBeVisible();

    await page.getByLabel(/Provider Name/).fill(TEST_PROVIDER_NAME);
    await page.getByLabel('API Key').fill('sk-test-e2e-not-a-real-key');

    // ProviderBrandSelect is a searchable combobox; open it and pick "openai".
    await page.getByRole('combobox').or(page.getByPlaceholder(/brand|provider/i)).first().click();
    await page.getByText('OpenAI', { exact: false }).first().click();

    await page.getByRole('button', { name: 'Create' }).click();

    // On success the dialog closes and the new provider card appears in the grid.
    await expect(page.getByText(TEST_PROVIDER_NAME)).toBeVisible({ timeout: 10000 });
  });

  test('creating a provider without a name shows a validation error', async ({ page }) => {
    await page.goto('providers');

    await page.getByRole('button', { name: 'Add Provider' }).click();
    await page.getByLabel('API Key').fill('sk-test-e2e-not-a-real-key');
    // Deliberately leave Provider Name blank — required=true on the input,
    // so the browser's own constraint validation should block submission
    // (or the backend rejects it with a toast if that's bypassed).
    await page.getByRole('button', { name: 'Create' }).click();

    const nameInput = page.getByLabel(/Provider Name/);
    await expect(nameInput).toHaveJSProperty('validity.valid', false);
  });
});
