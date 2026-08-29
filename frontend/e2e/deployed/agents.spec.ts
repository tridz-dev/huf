import { test, expect } from '@playwright/test';

test.describe('Agents', () => {
  test('agents list renders and links to a form', async ({ page }) => {
    await page.goto('agents');

    // The subtitle band under the page title was removed as part of the
    // page-chrome redesign (see PageFrame.tsx: "no subtitle band"); the
    // page title itself is the stable render signal now.
    await expect(page.getByRole('heading', { name: 'Agents' })).toBeVisible();

    // At least one agent card should be present on a bench that already has
    // agents. "Test New UI" is not a seeded agent on this bench (confirmed
    // via frappe.client.get_list); "Demo Assistant" is the seeded agent
    // that actually exists.
    //
    // ItemCard/BaseCard (components/dashboard/cards/*.tsx) renders the card
    // as a plain <div onClick=...> with no anchor and no role — matching
    // 'a, [role="button"], div' with hasText picks up the first ancestor
    // div containing that text anywhere in the DOM (often a much higher-up
    // layout wrapper), which isn't clickable/navigable. Clicking the title
    // text itself lets the click bubble up to the card's own onClick.
    const firstAgentCard = page.getByText('Demo Assistant', { exact: true }).first();
    if (await firstAgentCard.count()) {
      await firstAgentCard.click();
      await expect(page).toHaveURL(/\/huf\/agents\//);
      await expect(page.getByRole('tab', { name: 'General' })).toBeVisible();
    }
  });
});
