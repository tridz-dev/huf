import { Page } from '@playwright/test';

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
}

function cssEscape(id: string): string {
  return id.replace(/([^a-zA-Z0-9_-])/g, '\\$1');
}
