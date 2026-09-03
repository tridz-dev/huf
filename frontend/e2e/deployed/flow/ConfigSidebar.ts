import { expect, Page } from '@playwright/test';

/**
 * Page object for RightSidebar.tsx (node/edge/flow config panel).
 *
 * The panel has no wrapping test id, but every field follows the same
 * radix pattern: `<Label htmlFor="x">Text</Label>` paired with an element
 * whose `id="x"` is an Input, textarea, or a Select's SelectTrigger. We
 * drive everything off that `htmlFor` → `id` link rather than guessing at
 * container structure, which makes this resilient to layout changes even
 * without test ids.
 */
export class ConfigSidebar {
  constructor(private readonly page: Page) {}

  /** All field labels currently rendered in the sidebar, in DOM order. */
  async listFieldLabels(): Promise<string[]> {
    const labels = this.page.locator('label[for]');
    const count = await labels.count();
    const out: string[] = [];
    for (let i = 0; i < count; i++) {
      const text = (await labels.nth(i).innerText()).trim();
      if (text) out.push(text);
    }
    return out;
  }

  private labelFor(labelText: string) {
    return this.page.locator('label[for]', { hasText: labelText }).first();
  }

  private async controlFor(labelText: string) {
    const label = this.labelFor(labelText);
    const id = await label.getAttribute('for');
    if (!id) throw new Error(`Field "${labelText}" has no htmlFor target`);
    return this.page.locator(`#${cssEscape(id)}`);
  }

  /**
   * Fill a field by its label text. Handles plain inputs/textareas directly;
   * for a radix Select (id lives on the SelectTrigger button), opens the
   * dropdown and picks the option whose text matches `value`.
   */
  async fillField(labelText: string, value: string): Promise<void> {
    const control = await this.controlFor(labelText);
    const tag = await control.evaluate((el) => el.tagName.toLowerCase());
    const role = await control.getAttribute('role');

    if (tag === 'input' || tag === 'textarea') {
      await control.fill(value);
      return;
    }
    if (role === 'combobox' || tag === 'button') {
      // Radix Select trigger (or the Combobox component) — open then pick.
      await control.click();
      const option = this.page.getByRole('option', { name: value }).first();
      await option.click();
      return;
    }
    throw new Error(`Don't know how to fill field "${labelText}" (tag=${tag}, role=${role})`);
  }

  /** Read a field's current value back (input value, or a Select's displayed text). */
  async readField(labelText: string): Promise<string> {
    const control = await this.controlFor(labelText);
    const tag = await control.evaluate((el) => el.tagName.toLowerCase());
    if (tag === 'input' || tag === 'textarea') {
      return control.inputValue();
    }
    return (await control.innerText()).trim();
  }

  /**
   * Locate a radix `<Checkbox>`'s trigger button by its paired label text.
   * Unlike Selects, Checkbox usages in RightSidebar.tsx DO pass a real
   * `id` matching the Label's `htmlFor`, so this reuses controlFor — but
   * fillField()/readField() don't know how to drive a checkbox's
   * `data-state` (they'd misfire fillField's combobox branch, which opens
   * the control and looks for a role="option" that never appears). These
   * two methods are the dedicated checkbox path.
   */
  async isChecked(labelText: string): Promise<boolean> {
    const control = await this.controlFor(labelText);
    return (await control.getAttribute('data-state')) === 'checked';
  }

  async setChecked(labelText: string, checked: boolean): Promise<void> {
    if ((await this.isChecked(labelText)) !== checked) {
      const control = await this.controlFor(labelText);
      await control.click();
    }
  }

  /**
   * Locate a `Combobox` (ui/combobox.tsx) trigger button by its paired
   * label text. Unlike Input/Select fields, every Combobox usage in
   * RightSidebar.tsx (Agent, Tool, Routing Agent, Approver Role,
   * Reference DocType, Attributed Agent pickers) omits the `id` prop
   * entirely — the component doesn't even accept one — so the Label's
   * `htmlFor` points at an id that exists nowhere in the DOM and
   * controlFor()/fillField() cannot find these fields at all. This walks
   * forward in document order from the label to the next
   * `button[role="combobox"]` instead of relying on the (broken) for/id
   * link.
   */
  private comboboxTriggerFor(labelText: string) {
    const label = this.page.locator('label', { hasText: labelText }).first();
    return label.locator('xpath=following::button[@role="combobox"][1]');
  }

  async fillCombobox(labelText: string, optionText: string | RegExp): Promise<void> {
    const trigger = this.comboboxTriggerFor(labelText);
    await trigger.click();
    const option = this.page.getByRole('option', { name: optionText }).first();
    await option.click();
  }

  async readCombobox(labelText: string): Promise<string> {
    const trigger = this.comboboxTriggerFor(labelText);
    // A combobox in this sidebar can flip Loading... -> placeholder -> Loading...
    // as two independent fetches resolve (the flow tool list and the agent
    // list). So a single "is it no longer Loading" check can pass in the gap
    // between them and the very next read still returns "Loading...", which
    // then surfaces as a bogus "the saved value was lost" failure.
    // Poll until the text is BOTH non-loading AND stable across two reads.
    let last = '';
    await expect
      .poll(
        async () => {
          const now = (await trigger.innerText()).trim();
          const stable = now === last && !/^Loading\.\.\.$/.test(now);
          last = now;
          return stable ? now : `__unstable__:${now}`;
        },
        { timeout: 45000, intervals: [200, 300, 500, 1000, 2000] },
      )
      .not.toMatch(/^__unstable__:/);
    return last;
  }

}

function cssEscape(id: string): string {
  return id.replace(/([^a-zA-Z0-9_-])/g, '\\$1');
}
