import { describe, expect, it } from 'vitest';
import { bandForWidth, clampPanelWidth, defaultPanelWidth, panelLayout, sheetMaxWidth, viewportFor } from './responsive';

describe('bandForWidth', () => {
  it.each([
    [1920, 'xl'], [1440, 'xl'], [1439, 'lg'], [1200, 'lg'], [1199, 'md'], [1024, 'md'], [1023, 'sm'], [768, 'sm'], [767, 'xs'], [390, 'xs'],
  ])('%i px is %s', (width, band) => expect(bandForWidth(width)).toBe(band));
});

describe('viewportFor', () => {
  it('folds the header and the navigation at 1200 and below', () => {
    expect(viewportFor(1201).isCompact).toBe(false);
    expect(viewportFor(1200).isCompact).toBe(true);
  });
  it('uses touch sizes below 1024 and phone rules below 768', () => {
    expect(viewportFor(1024).isTouch).toBe(false);
    expect(viewportFor(1023).isTouch).toBe(true);
    expect(viewportFor(768).isPhone).toBe(false);
    expect(viewportFor(767).isPhone).toBe(true);
  });
});

describe('step panel width', () => {
  it('stays between 300 and 480', () => {
    expect(clampPanelWidth(120)).toBe(300);
    expect(clampPanelWidth(900)).toBe(480);
    expect(clampPanelWidth(412.4)).toBe(412);
    expect(clampPanelWidth(Number.NaN)).toBe(300);
  });
  it('starts wider on a big screen', () => {
    expect(defaultPanelWidth(1600)).toBe(360);
    expect(defaultPanelWidth(1100)).toBe(340);
    expect(defaultPanelWidth(900)).toBe(300);
  });
});

describe('panelLayout', () => {
  it('docks beside the canvas while the canvas keeps 520px', () => {
    // 1440 wide, app navigation 248: 1192 for the editor -> 1192 - 48 - 520 = 624 spare, so a 360 panel fits
    expect(panelLayout(1192, 360)).toEqual({ mode: 'docked', width: 360 });
  });
  it('narrows the panel before it takes the canvas below 520px', () => {
    // 1024 with the navigation as a 64px rail: 960 -> 960 - 48 - 520 = 392 spare: a 480 request becomes 392
    expect(panelLayout(960, 480)).toEqual({ mode: 'docked', width: 392 });
  });
  it('opens over the canvas when even the narrowest panel would squeeze it', () => {
    // 768 with the rail: 704 -> 704 - 48 - 520 = 136 spare: not enough for a 300 panel
    expect(panelLayout(704, 360)).toEqual({ mode: 'sheet' });
  });
});

describe('sheetMaxWidth', () => {
  it('is 62% of the window', () => {
    expect(sheetMaxWidth(1024)).toBe(635);
    expect(sheetMaxWidth(768)).toBe(476);
  });
});
