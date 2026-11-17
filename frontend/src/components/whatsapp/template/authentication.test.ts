import { describe, expect, it } from 'vitest';
import type { TemplateDetail } from '@/services/whatsappApi';
import { applyAuthenticationFormat, emptyDraft } from './draft';
import { fromTemplateDetail, toCreatePayload, toEditPayload } from './payload';
import { canSubmit, validateDraft } from './rules';

const auth = (over = {}) => applyAuthenticationFormat({ ...emptyDraft('AUTHENTICATION'), name: 'login_code', ...over });

describe('authentication drafts', () => {
  it('derives the fixed body, footer and copy-code button', () => {
    const d = auth({ securityRecommendation: true, codeExpiryMinutes: 5, otpButtonText: 'Copy' });
    expect(d.body).toBe('{{1}} is your verification code. For your security, do not share this code.');
    expect(d.footer).toBe('This code expires in 5 minutes.');
    expect(d.buttons).toHaveLength(1);
    expect(d.buttons[0]).toMatchObject({ type: 'COPY_CODE', text: 'Copy' });
    const bare = auth({ securityRecommendation: false, codeExpiryMinutes: null });
    expect(bare.body).toBe('{{1}} is your verification code.');
    expect(bare.footer).toBe('');
  });

  it('leaves non-authentication drafts alone', () => {
    const d = { ...emptyDraft('UTILITY'), body: 'x' };
    expect(applyAuthenticationFormat(d)).toBe(d);
  });

  it('sends only the options in the create payload', () => {
    expect(toCreatePayload(auth({ codeExpiryMinutes: 10, otpButtonText: ' ' }))).toEqual({
      template_name: 'login_code',
      category: 'AUTHENTICATION',
      language_code: 'en_US',
      template: '',
      parameter_format: 'POSITIONAL',
      add_security_recommendation: true,
      code_expiration_minutes: 10,
      otp_button_text: 'Copy code',
    });
    expect(toCreatePayload(auth({ codeExpiryMinutes: null })).code_expiration_minutes).toBeUndefined();
    expect(toEditPayload(auth())).not.toHaveProperty('template_name');
    expect(toEditPayload(auth())).not.toHaveProperty('buttons');
  });

  it('validates expiry and button label', () => {
    expect(canSubmit(auth())).toBe(true);
    expect(validateDraft(auth({ codeExpiryMinutes: 0 })).codeExpiryMinutes).toBeTruthy();
    expect(validateDraft(auth({ codeExpiryMinutes: 91 })).codeExpiryMinutes).toBeTruthy();
    expect(validateDraft(auth({ codeExpiryMinutes: 1.5 })).codeExpiryMinutes).toBeTruthy();
    expect(validateDraft(auth({ otpButtonText: 'x'.repeat(26) })).otpButtonText).toBeTruthy();
    expect(validateDraft(auth({ name: '' })).name).toBeTruthy();
  });

  it('prefills the wizard from a stored authentication template', () => {
    const detail = {
      template_name: 'login_code',
      language_code: 'en_US',
      category: 'AUTHENTICATION',
      components: {
        header: null,
        body: { text: '{{1}} is your verification code. For your security, do not share this code.', sample_values: [] },
        footer: { text: 'This code expires in 15 minutes.' },
        buttons: [{ type: 'OTP', text: 'Copy code' }],
      },
    } as unknown as TemplateDetail;
    const d = fromTemplateDetail(detail);
    expect(d).toMatchObject({ category: 'AUTHENTICATION', securityRecommendation: true, codeExpiryMinutes: 15, otpButtonText: 'Copy code' });
  });
});
