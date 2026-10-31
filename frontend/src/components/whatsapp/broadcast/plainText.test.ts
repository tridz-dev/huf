import { describe, expect, it } from 'vitest';
import { categoryLabel, costWarningText, failureDetail, reasonText, recipientStatusLabel } from './plainText';

describe('plain broadcast wording', () => {
  it('explains rate_unavailable without the code', () => {
    const t = costWarningText('rate_unavailable:utility:US');
    expect(t).toContain('price estimate is not available yet');
    expect(t).toContain('United States');
    expect(t).not.toMatch(/rate_unavailable|utility:US|_/);
  });
  it('maps other cost warnings and falls back generically', () => {
    expect(costWarningText('category_missing')).toMatch(/no category/);
    expect(costWarningText('market_unknown:3_recipients')).toContain('3 numbers');
    expect(costWarningText('something_new:x')).toBe('Some details of the price estimate are not available yet.');
  });
  it('labels categories, statuses and reasons', () => {
    expect(categoryLabel('MARKETING')).toBe('Marketing');
    expect(categoryLabel(undefined)).toBe('Not set');
    expect(recipientStatusLabel('deferred')).toBe('Will send later');
    expect(reasonText('opted_out')).toMatch(/not to receive/);
    expect(reasonText('invalid_params: body missing')).not.toMatch(/_|:/);
    expect(reasonText('brand_new_code')).not.toContain('_');
    expect(failureDetail('', 131026)).toBe('This number is not on WhatsApp.');
    expect(failureDetail('raw meta text', 999999)).toBe('WhatsApp could not deliver this message.');
    expect(failureDetail('raw meta text', 999999)).not.toContain('raw');
    expect(failureDetail('', 131049)).toMatch(/limits marketing messages/);
    expect(recipientStatusLabel('unknown')).toBe('Waiting for WhatsApp to confirm');
    expect(recipientStatusLabel('brand_new')).toBe('Waiting for WhatsApp to confirm');
    expect(reasonText('blocked')).toBe('This person has blocked the number');
    expect(reasonText('zzz')).toBe('Not sent for another reason');
    expect(categoryLabel('UTILITY')).toBe('Order and account updates');
  });
  it('words the price note without codes', () => {
    expect(costWarningText('rate_unavailable:utility:US')).toBe('The price estimate is not available yet for order and account updates sent to the United States, so the total is left out.');
    expect(costWarningText('rate_unavailable:marketing:ZZ')).toMatch(/marketing messages to one country/);
    expect(costWarningText('rate_unavailable::ZZ')).toBe('The price estimate is not available yet for messages to one country, so the total is left out.');
  });
});
