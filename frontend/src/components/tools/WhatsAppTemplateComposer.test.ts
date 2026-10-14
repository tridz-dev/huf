import { describe, expect, it } from 'vitest';
import { DEFAULT_WHATSAPP_TEMPLATE_VALUE, buildTemplateArgs } from './WhatsAppTemplateComposer';

const base = { ...DEFAULT_WHATSAPP_TEMPLATE_VALUE, template_name: ' order_update ' };

describe('buildTemplateArgs', () => {
  it('omits header and button params when unset', () => {
    expect(buildTemplateArgs(base)).toEqual({ template_name: 'order_update', language_code: 'en_US', parameters: [] });
  });
  it('builds text header and url button suffixes', () => {
    const args = buildTemplateArgs({
      ...base,
      header_kind: 'text',
      header_value: ' Order 1 ',
      url_buttons: [{ index: 1, text: ' a/b ' }, { index: 2, text: '  ' }],
    });
    expect(args.header_params).toEqual(['Order 1']);
    expect(args.button_params).toEqual([{ index: 1, sub_type: 'url', text: 'a/b' }]);
  });
  it('builds media header', () => {
    const args = buildTemplateArgs({ ...base, header_kind: 'image', header_value: 'https://x.io/a.png' });
    expect(args.header_params).toEqual([{ type: 'image', link: 'https://x.io/a.png' }]);
  });
});
