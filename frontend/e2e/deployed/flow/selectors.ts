/**
 * Centralised selectors for the flow-builder e2e harness.
 *
 * There are almost no `data-testid`s in this frontend (two exist, both in
 * chat components; none in flow components). Everything below is
 * text/role-based and therefore fragile to copy changes. Keeping every
 * selector in this one file means a future pass that adds `data-testid`s
 * only needs to edit here.
 */
import { Locator, Page } from '@playwright/test';

export const selectors = {
  flowsList: {
    // FlowsListHeaderActions.tsx: <Button>{creating ? 'Creating...' : 'New Flow'}</Button>
    newFlowButton: (page: Page): Locator => page.getByRole('button', { name: /new flow/i }),

    // ItemCard renders each flow as a clickable card with the flow name as a heading-like title.
    // Scope to the grid to avoid colliding with anything else on the page.
    grid: (page: Page): Locator => page.locator('[class*="grid"]').first(),

    // A flow card, matched by its title text. ItemCard has no test id, so we
    // match on the card's title node and walk up to the clickable container.
    cardByName: (page: Page, name: string): Locator =>
      page
        .locator('div')
        .filter({ has: page.getByText(name, { exact: true }) })
        .last(),

    // The 'Configure' action (gear icon button) inside a given card.
    configureAction: (card: Locator): Locator => card.getByRole('button', { name: /configure/i }),

    emptyState: (page: Page): Locator => page.getByText('No flows have been created yet.'),
  },

  canvas: {
    // ReactFlow root; canvas nodes and edges all live inside this container.
    // Scoping here is what lets us disambiguate a canvas node from a modal
    // card that happens to share the same label (FlowCanvas.tsx labelMap
    // reuses palette-card strings).
    root: (page: Page): Locator => page.locator('.react-flow'),

    nodeByLabel: (page: Page, label: string): Locator =>
      selectors.canvas.root(page).getByText(label, { exact: true }),

    // ActionNode.tsx / TriggerNode.tsx: the add-node "+" button is rendered
    // `absolute -bottom-6 ... opacity-0 group-hover:opacity-100`, unnamed,
    // icon-only. It is the only <button> inside the node's `.group`
    // container that is NOT the delete (Trash2) button, so we select by
    // position: last button in the node wrapper.
    addButtonForNode: (nodeEl: Locator): Locator => nodeEl.locator('button').last(),

    // The node wrapper (`.group` div) that directly contains a given label,
    // used so we can `.hover()` it before the add button becomes clickable.
    nodeWrapperByLabel: (page: Page, label: string): Locator =>
      selectors.canvas.root(page).locator('.group', { has: page.getByText(label, { exact: true }) }).first(),

    // FlowsHeaderActions.tsx renders Save/Runs/Settings/Run/Publish together
    // in one container — 'Publish' only appears there (there's also a
    // sidebar nav item literally named "Settings", so an unscoped
    // getByRole('button', {name:'Settings'}) is ambiguous). Scope every
    // header action to that container, keyed off the unique 'Publish' button.
    headerActionsGroup: (page: Page): Locator =>
      page
        .locator('div')
        .filter({ has: page.getByRole('button', { name: /^publish$/i }) })
        .last(),

    saveButton: (page: Page): Locator => selectors.canvas.headerActionsGroup(page).getByRole('button', { name: /^save$/i }),
    runButton: (page: Page): Locator => selectors.canvas.headerActionsGroup(page).getByRole('button', { name: /^run$/i }),
    saveStateIndicator: (page: Page): Locator => page.getByText(/^(Saved|Unsaved|Saving\.\.\.|Save Failed)$/),

    settingsButton: (page: Page): Locator =>
      selectors.canvas.headerActionsGroup(page).getByRole('button', { name: /^settings$/i }),
  },

  nodeModal: {
    dialog: (page: Page): Locator => page.getByRole('dialog'),
    searchInput: (page: Page): Locator => selectors.nodeModal.dialog(page).getByPlaceholder(/search/i),
    triggersTab: (page: Page): Locator => selectors.nodeModal.dialog(page).getByRole('tab', { name: /^triggers$/i }),
    actionsTab: (page: Page): Locator => selectors.nodeModal.dialog(page).getByRole('tab', { name: /^actions$/i }),
    exploreSubTab: (page: Page): Locator => selectors.nodeModal.dialog(page).getByRole('tab', { name: /^explore$/i }),
    // Card buttons in both the trigger-explore grid and the action category
    // grids share this shape: <button><div>Icon</div><div><div>Name</div>...
    cardButtons: (page: Page): Locator =>
      selectors.nodeModal.dialog(page).locator('button').filter({ hasText: /.+/ }),
    cardByName: (page: Page, name: string): Locator =>
      selectors.nodeModal.dialog(page).getByRole('button', { name: new RegExp(`^${escapeRegex(name)}`) }),
    saveConfigurationButton: (page: Page): Locator =>
      selectors.nodeModal.dialog(page).getByRole('button', { name: /save configuration/i }),
  },

  configSidebar: {
    // RightSidebar.tsx has no wrapping test id; it's the aside-like panel
    // that appears once a node/edge is selected. We scope to the last
    // fixed-width flex container on the right, identified here by the
    // presence of a <Label> element (radix Label renders as <label>).
    root: (page: Page): Locator => page.locator('label').first().locator('xpath=ancestor::*[self::div][1]/ancestor::div').first(),
    // Simpler and more robust: every field is a <Label for="id"> paired with
    // an element carrying that id (Input/Select/Combobox trigger/textarea).
    fieldByLabel: (page: Page, labelText: string): Locator => {
      const label = page.locator('label', { hasText: labelText }).first();
      return label;
    },
  },
};

function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
