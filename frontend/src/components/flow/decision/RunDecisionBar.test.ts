import { describe, expect, it } from 'vitest';
import { whyCannotDecide } from './RunDecisionBar';

describe('whyCannotDecide', () => {
  it('names the role in plain words', () => {
    expect(whyCannotDecide("You do not have the required role 'Huf User' to decide this approval")).toBe('Only people with the Huf User role can approve or reject this one.');
  });
  it('covers the system manager and named-approver refusals', () => {
    expect(whyCannotDecide('Only a System Manager may decide this approval')).toBe('Only a system manager can approve or reject this one.');
    expect(whyCannotDecide('You are not an authorised approver for this flow run')).toBe('Only the people named for this approval can approve or reject it.');
  });
  it('has a sentence when the server said nothing', () => {
    expect(whyCannotDecide(null)).toBe('Only the people chosen for this approval can approve or reject it.');
  });
});
