import { describe, expect, it } from 'vitest';
import { showSaveStatus } from './saveStatus';

describe('showSaveStatus', () => {
  it('is shown to someone who can edit the flow on a larger screen', () => {
    expect(showSaveStatus({ hasFlow: true, isPhone: false, canManage: true })).toBe(true);
  });
  it('is hidden for a flow the person can only view', () => {
    expect(showSaveStatus({ hasFlow: true, isPhone: false, canManage: false })).toBe(false);
  });
  it('is hidden on a phone and while no flow is open', () => {
    expect(showSaveStatus({ hasFlow: true, isPhone: true, canManage: true })).toBe(false);
    expect(showSaveStatus({ hasFlow: false, isPhone: false, canManage: true })).toBe(false);
  });
});
