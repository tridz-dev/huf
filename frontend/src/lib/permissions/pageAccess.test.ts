import { describe, expect, it } from 'vitest';
import { PAGE_ACCESS, PAGE_ACCESS_ANY, hasPageAccess } from './pageAccess';

describe('hasPageAccess', () => {
  it('lets anyone through a page with no requirement', () => {
    expect(hasPageAccess([], undefined)).toBe(true);
  });
  it('turns away a person with no capabilities from everything', () => {
    for (const required of Object.values(PAGE_ACCESS)) expect(hasPageAccess([], required)).toBe(false);
    expect(hasPageAccess([], PAGE_ACCESS_ANY)).toBe(false);
  });
  it('accepts any one of a list', () => {
    expect(hasPageAccess(['flows.manage'], PAGE_ACCESS.settings)).toBe(true);
    expect(hasPageAccess(['flows.use'], PAGE_ACCESS.settings)).toBe(false);
  });
  it('"any" means some Huf role', () => {
    expect(hasPageAccess(['chat.view_own'], PAGE_ACCESS_ANY)).toBe(true);
  });
  it('keeps the viewer role out of the manager pages but in the agent list', () => {
    const viewer = ['data.records.view_own', 'chat.view_own', 'agent.use'];
    expect(hasPageAccess(viewer, PAGE_ACCESS.agents)).toBe(true);
    expect(hasPageAccess(viewer, PAGE_ACCESS.dashboard)).toBe(false);
    expect(hasPageAccess(viewer, PAGE_ACCESS.settings)).toBe(false);
    expect(hasPageAccess(viewer, PAGE_ACCESS.flows)).toBe(false);
  });
});
